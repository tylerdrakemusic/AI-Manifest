"""Tests for the ElevenLabs client."""

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.elevenlabs.client import ElevenLabsClient


@pytest.fixture
def client() -> ElevenLabsClient:
    """Create a client with a fake API key (no real calls)."""
    return ElevenLabsClient(api_key="test-key-not-real")


class TestListVoices:
    def test_returns_voice_list(self, client: ElevenLabsClient) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "voices": [{"voice_id": "abc", "name": "TestVoice"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("src.integrations.elevenlabs.client.httpx.get", return_value=mock_resp):
            voices = client.list_voices()
            assert len(voices) == 1
            assert voices[0]["name"] == "TestVoice"


class TestTextToSpeech:
    def test_returns_audio_bytes(self, client: ElevenLabsClient) -> None:
        mock_resp = MagicMock()
        mock_resp.content = b"\xff\xfb\x90\x00"  # fake mp3 header bytes
        mock_resp.raise_for_status = MagicMock()

        with patch("src.integrations.elevenlabs.client.httpx.post", return_value=mock_resp):
            audio = client.text_to_speech("Hello", "voice123")
            assert isinstance(audio, bytes)
            assert len(audio) > 0


class TestSaveSpeech:
    def test_saves_to_file(self, client: ElevenLabsClient, tmp_path) -> None:
        mock_resp = MagicMock()
        mock_resp.content = b"\xff\xfb\x90\x00"
        mock_resp.raise_for_status = MagicMock()

        out_file = tmp_path / "test_output.mp3"
        with patch("src.integrations.elevenlabs.client.httpx.post", return_value=mock_resp):
            result = client.save_speech("Hello", "voice123", out_file)
            assert result.exists()
            assert result.read_bytes() == b"\xff\xfb\x90\x00"
