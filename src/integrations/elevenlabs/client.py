"""ElevenLabs API client — re-export shim.

The canonical implementation lives in the shared workspace integration library:
    f:\\⊕Workspace\\src\\integrations\\elevenlabs\\client.py

This module re-exports ElevenLabsClient for backwards compatibility with
existing 👁AI-Manifest imports.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the workspace client via absolute path to avoid module-name collision
# (both repos share the `src.integrations.elevenlabs` namespace).
_WORKSPACE_CLIENT = Path(r"f:\⊕Workspace\src\integrations\elevenlabs\client.py")
_WORKSPACE_SETTINGS = Path(r"f:\⊕Workspace\src\integrations\elevenlabs\settings.py")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_settings = _load_module("_workspace_elevenlabs_settings", _WORKSPACE_SETTINGS)
# The workspace client inlines its own constants, so just load it directly.
_client_mod = _load_module("_workspace_elevenlabs_client", _WORKSPACE_CLIENT)

ElevenLabsClient = _client_mod.ElevenLabsClient
DEFAULT_MODEL_ID = _settings.DEFAULT_MODEL_ID
DEFAULT_OUTPUT_FORMAT = _settings.DEFAULT_OUTPUT_FORMAT
DEFAULT_VOICE_SETTINGS = _settings.DEFAULT_VOICE_SETTINGS
STREAM_CHUNK_SIZE = _settings.STREAM_CHUNK_SIZE

__all__ = [
    "ElevenLabsClient",
    "DEFAULT_MODEL_ID",
    "DEFAULT_OUTPUT_FORMAT",
    "DEFAULT_VOICE_SETTINGS",
    "STREAM_CHUNK_SIZE",
]


class ElevenLabsClient:
    """Thin wrapper around the ElevenLabs REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or load_token("elevenlabs")
        self._headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Voices
    # ------------------------------------------------------------------

    def list_voices(self) -> list[dict]:
        """Return all available voices."""
        resp = httpx.get(f"{BASE_URL}/voices", headers=self._headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("voices", [])

    def get_voice(self, voice_id: str) -> dict:
        """Get details for a specific voice."""
        resp = httpx.get(
            f"{BASE_URL}/voices/{voice_id}", headers=self._headers, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Text-to-Speech
    # ------------------------------------------------------------------

    def text_to_speech(
        self,
        text: str,
        voice_id: str,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        voice_settings: dict | None = None,
    ) -> bytes:
        """Synthesize text to audio bytes."""
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings or DEFAULT_VOICE_SETTINGS,
        }
        resp = httpx.post(
            f"{BASE_URL}/text-to-speech/{voice_id}",
            headers=self._headers,
            json=payload,
            params={"output_format": output_format},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content

    def text_to_speech_stream(
        self,
        text: str,
        voice_id: str,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        voice_settings: dict | None = None,
    ) -> Iterator[bytes]:
        """Stream synthesized audio chunks."""
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings or DEFAULT_VOICE_SETTINGS,
        }
        with httpx.stream(
            "POST",
            f"{BASE_URL}/text-to-speech/{voice_id}/stream",
            headers=self._headers,
            json=payload,
            params={"output_format": output_format},
            timeout=60,
        ) as resp:
            resp.raise_for_status()
            yield from resp.iter_bytes(chunk_size=STREAM_CHUNK_SIZE)

    def save_speech(
        self, text: str, voice_id: str, output_path: str | Path, **kwargs
    ) -> Path:
        """Synthesize text and save to file."""
        audio = self.text_to_speech(text, voice_id, **kwargs)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(audio)
        return out

    # ------------------------------------------------------------------
    # User Info
    # ------------------------------------------------------------------

    def get_subscription_info(self) -> dict:
        """Return current subscription/usage info."""
        resp = httpx.get(
            f"{BASE_URL}/user/subscription", headers=self._headers, timeout=30
        )
        resp.raise_for_status()
        return resp.json()


# ------------------------------------------------------------------
# CLI quick-test
# ------------------------------------------------------------------

def _test_connection() -> None:
    """Quick connectivity test — list voices and print subscription."""
    client = ElevenLabsClient()
    print("=== ElevenLabs Connection Test ===\n")

    sub = client.get_subscription_info()
    print(f"Tier: {sub.get('tier', 'unknown')}")
    print(f"Character quota: {sub.get('character_count', '?')}/{sub.get('character_limit', '?')}")
    print()

    voices = client.list_voices()
    print(f"Available voices: {len(voices)}")
    for v in voices[:5]:
        print(f"  - {v['name']} ({v['voice_id']})")
    if len(voices) > 5:
        print(f"  ... and {len(voices) - 5} more")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test_connection()
    else:
        print("Usage: python -m src.integrations.elevenlabs.client --test")
