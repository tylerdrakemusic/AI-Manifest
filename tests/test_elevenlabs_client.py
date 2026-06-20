"""Tests for the local ElevenLabs client (``src.integrations.elevenlabs``).

All HTTP calls are mocked via ``unittest.mock.patch`` — no real ElevenLabs
API calls are made. The client is constructed with a fake ``api_key`` so
tests do not require ``ELEVENLABS_API_KEY`` to be set.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.elevenlabs.client import ElevenLabsClient

_PATCH_PREFIX = "src.integrations.elevenlabs.client.httpx"


@pytest.fixture
def client() -> ElevenLabsClient:
    """Create a client with a fake API key (no real calls)."""
    return ElevenLabsClient(api_key="test-key-not-real")


def test_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    with pytest.raises(EnvironmentError, match="ElevenLabs API key not found"):
        ElevenLabsClient()


def test_resolves_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-key")

    client = ElevenLabsClient()
    assert client._api_key == "env-key"
    assert client._headers["xi-api-key"] == "env-key"


class TestListVoices:
    def test_returns_voice_list(self, client: ElevenLabsClient) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "voices": [{"voice_id": "abc", "name": "TestVoice"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{_PATCH_PREFIX}.get", return_value=mock_resp) as mock_get:
            voices = client.list_voices()
            assert len(voices) == 1
            assert voices[0]["name"] == "TestVoice"
            mock_get.assert_called_once_with(
                "https://api.elevenlabs.io/v1/voices",
                headers=client._headers,
                timeout=30,
            )


class TestGetVoice:
    def test_returns_voice_details(self, client: ElevenLabsClient) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"voice_id": "voice123", "name": "TestVoice"}
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{_PATCH_PREFIX}.get", return_value=mock_resp) as mock_get:
            details = client.get_voice("voice123")
            assert details["voice_id"] == "voice123"
            mock_get.assert_called_once_with(
                "https://api.elevenlabs.io/v1/voices/voice123",
                headers=client._headers,
                timeout=30,
            )


class TestTextToSpeech:
    def test_returns_audio_bytes(self, client: ElevenLabsClient) -> None:
        mock_resp = MagicMock()
        mock_resp.content = b"\xff\xfb\x90\x00"  # fake mp3 header bytes
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{_PATCH_PREFIX}.post", return_value=mock_resp) as mock_post:
            audio = client.text_to_speech("Hello", "voice123")
            assert isinstance(audio, bytes)
            assert len(audio) > 0
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            assert kwargs["params"] == {"output_format": "mp3_44100_128"}


class TestTextToSpeechStream:
    def test_streams_audio_chunks(self, client: ElevenLabsClient) -> None:
        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_stream
        mock_stream.__exit__.return_value = None
        mock_stream.iter_bytes.return_value = [b"part1", b"part2"]
        mock_stream.raise_for_status = MagicMock()

        with patch(f"{_PATCH_PREFIX}.stream", return_value=mock_stream) as mock_stream_func:
            chunks = list(client.text_to_speech_stream("Hello", "voice123"))
            assert chunks == [b"part1", b"part2"]
            mock_stream_func.assert_called_once()


class TestSaveSpeech:
    def test_saves_to_file(self, client: ElevenLabsClient, tmp_path) -> None:
        mock_resp = MagicMock()
        mock_resp.content = b"\xff\xfb\x90\x00"
        mock_resp.raise_for_status = MagicMock()

        out_file = tmp_path / "test_output.mp3"
        with patch(f"{_PATCH_PREFIX}.post", return_value=mock_resp):
            result = client.save_speech("Hello", "voice123", out_file)
            assert result.exists()
            assert result.read_bytes() == b"\xff\xfb\x90\x00"


class TestGetSubscriptionInfo:
    def test_returns_subscription_info(self, client: ElevenLabsClient) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tier": "free", "character_count": 1000}
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{_PATCH_PREFIX}.get", return_value=mock_resp) as mock_get:
            info = client.get_subscription_info()
            assert info["tier"] == "free"
            mock_get.assert_called_once_with(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers=client._headers,
                timeout=30,
            )
