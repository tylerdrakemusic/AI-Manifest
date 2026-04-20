"""ElevenLabs API client — voice synthesis, listing, and streaming."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import httpx

from src.config.elevenlabs_settings import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_SETTINGS,
    STREAM_CHUNK_SIZE,
)
from src.utils.tokens import load_token

BASE_URL = "https://api.elevenlabs.io/v1"


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
