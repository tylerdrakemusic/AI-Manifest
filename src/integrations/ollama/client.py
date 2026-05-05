"""Mirrored Ollama HTTP client for 👁AI-Manifest.

Self-contained CI-safe copy of the workspace canonical client
(``⊕Workspace/src/integrations/ollama/client.py``).  No cross-project
``sys.path`` manipulation required — import directly::

    from src.integrations.ollama import OllamaClient

Environment variables
---------------------
OLLAMA_BASE_URL : base URL of the running Ollama server
    Default: http://localhost:11434
OLLAMA_MODEL : model tag to use for generation
    Default: llama3.1:8b
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"

_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 120.0
_TIMEOUT = httpx.Timeout(
    connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=10.0, pool=5.0
)

_GENERATE_ENDPOINT = "/api/generate"
_TAGS_ENDPOINT = "/api/tags"
_HEALTH_ENDPOINT = "/"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OllamaError(RuntimeError):
    """Raised when the Ollama API returns an error or is unreachable."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OllamaClient:
    """Thin, synchronous HTTP client for the Ollama REST API.

    All network calls use explicit timeouts and raise :class:`OllamaError`
    on any non-2xx response or connection failure.

    Attribute resolution order:
    1. Constructor argument
    2. Environment variable (``OLLAMA_BASE_URL`` / ``OLLAMA_MODEL``)
    3. Built-in default
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Return ``True`` if the Ollama server is reachable, ``False`` otherwise."""
        try:
            resp = httpx.get(
                self.base_url + _HEALTH_ENDPOINT,
                timeout=httpx.Timeout(
                    connect=_CONNECT_TIMEOUT, read=5.0, write=5.0, pool=5.0
                ),
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def list_models(self) -> list[dict[str, Any]]:
        """Return the list of locally available model metadata dicts.

        Raises
        ------
        OllamaError
            If the API call fails or returns a non-2xx status.
        """
        resp = self._get(_TAGS_ENDPOINT)
        return resp.get("models", [])

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        """Send *prompt* to the model and return the full response text.

        Parameters
        ----------
        prompt:
            The text prompt to send.
        model:
            Override the instance model for this call only.

        Returns
        -------
        str
            The model's response text.

        Raises
        ------
        OllamaError
            If the API call fails or returns a non-2xx status.
        """
        payload: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
        }
        resp = self._post(_GENERATE_ENDPOINT, payload)
        response_text = resp.get("response")
        if response_text is None:
            raise OllamaError(
                "Unexpected Ollama response: 'response' key missing. "
                f"Keys present: {list(resp.keys())}"
            )
        return str(response_text)

    def ensure_model_available(self, model: str | None = None) -> bool:
        """Return ``True`` if *model* is present in the local Ollama model list.

        Parameters
        ----------
        model:
            Model tag to check. Defaults to the instance model.

        Returns
        -------
        bool
            ``True`` when found locally, ``False`` otherwise (including when
            the server is unreachable).
        """
        target = model or self.model
        try:
            models = self.list_models()
        except OllamaError:
            return False
        return any(
            m.get("name") == target or m.get("model") == target
            for m in models
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        try:
            resp = httpx.get(self.base_url + path, timeout=_TIMEOUT)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}: {exc}"
            ) from exc
        return self._parse(resp, path)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = httpx.post(
                self.base_url + path,
                json=payload,
                timeout=_TIMEOUT,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}: {exc}"
            ) from exc
        return self._parse(resp, path)

    @staticmethod
    def _parse(resp: httpx.Response, path: str) -> dict[str, Any]:
        if resp.status_code != 200:
            raise OllamaError(
                f"Ollama API error on {path}: "
                f"HTTP {resp.status_code} — {resp.text[:200]}"
            )
        try:
            return resp.json()
        except Exception as exc:
            raise OllamaError(
                f"Failed to parse Ollama JSON response from {path}: {exc}"
            ) from exc
