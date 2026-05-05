"""Tests for the mirrored Ollama client (src.integrations.ollama).

All HTTP calls are mocked via unittest.mock.patch — no real Ollama server
required. Tests verify request construction, response parsing, and error
handling mirror the workspace canonical client contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.ollama.client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OllamaClient,
    OllamaError,
)

_PATCH_HTTPX = "src.integrations.ollama.client.httpx"


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(base_url="http://test-ollama:11434", model="test-model")


# ---------------------------------------------------------------------------
# OllamaClient construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        c = OllamaClient()
        assert c.base_url == DEFAULT_BASE_URL
        assert c.model == DEFAULT_MODEL

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom:9999/")
        monkeypatch.setenv("OLLAMA_MODEL", "mistral:7b")
        c = OllamaClient()
        assert c.base_url == "http://custom:9999"  # trailing slash stripped
        assert c.model == "mistral:7b"

    def test_constructor_arg_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://env:1234")
        monkeypatch.setenv("OLLAMA_MODEL", "env-model")
        c = OllamaClient(base_url="http://arg:5678", model="arg-model")
        assert c.base_url == "http://arg:5678"
        assert c.model == "arg-model"


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_returns_true_on_200(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            assert client.health_check() is True

    def test_returns_false_on_non_200(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            assert client.health_check() is False

    def test_returns_false_on_connect_error(self, client: OllamaClient) -> None:
        import httpx

        with patch(f"{_PATCH_HTTPX}.get", side_effect=httpx.ConnectError("refused")):
            assert client.health_check() is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


class TestListModels:
    def test_returns_model_list(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "llama3.1:8b"}, {"name": "mistral:7b"}]
        }
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            models = client.list_models()
        assert len(models) == 2
        assert models[0]["name"] == "llama3.1:8b"

    def test_raises_on_non_200(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal error"
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            with pytest.raises(OllamaError, match="HTTP 500"):
                client.list_models()


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_returns_response_text(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "7", "done": True}
        with patch(f"{_PATCH_HTTPX}.post", return_value=mock_resp) as mock_post:
            result = client.generate("Rate this task 1-10")
        assert result == "7"
        # Verify correct endpoint and payload shape
        call_kwargs = mock_post.call_args
        assert "/api/generate" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"]["model"] == "test-model"
        assert call_kwargs.kwargs["json"]["stream"] is False

    def test_model_override(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "5"}
        with patch(f"{_PATCH_HTTPX}.post", return_value=mock_resp) as mock_post:
            client.generate("prompt", model="override-model")
        assert mock_post.call_args.kwargs["json"]["model"] == "override-model"

    def test_raises_when_response_key_missing(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"done": True}  # no 'response' key
        with patch(f"{_PATCH_HTTPX}.post", return_value=mock_resp):
            with pytest.raises(OllamaError, match="'response' key missing"):
                client.generate("prompt")

    def test_raises_on_http_error(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "model not found"
        with patch(f"{_PATCH_HTTPX}.post", return_value=mock_resp):
            with pytest.raises(OllamaError, match="HTTP 404"):
                client.generate("prompt")

    def test_raises_on_connection_error(self, client: OllamaClient) -> None:
        import httpx

        with patch(
            f"{_PATCH_HTTPX}.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(OllamaError, match="Cannot reach Ollama"):
                client.generate("prompt")


# ---------------------------------------------------------------------------
# ensure_model_available
# ---------------------------------------------------------------------------


class TestEnsureModelAvailable:
    def test_returns_true_when_model_listed(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "test-model"}]}
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            assert client.ensure_model_available() is True

    def test_returns_false_when_model_not_listed(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "other-model"}]}
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            assert client.ensure_model_available() is False

    def test_returns_false_when_server_unreachable(self, client: OllamaClient) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "error"
        with patch(f"{_PATCH_HTTPX}.get", return_value=mock_resp):
            assert client.ensure_model_available() is False
