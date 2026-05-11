"""Focused tests for the vocal synthesis renderer seam contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.integrations.vocal_synthesis import (
    ExerciseMetadata,
    NoteEvent,
    VocalRenderRequest,
    render_vocal_exercise,
)


def _request(tmp_path: Path, stem: str = "exercise_take") -> VocalRenderRequest:
    return VocalRenderRequest(
        exercise=ExerciseMetadata(
            exercise_id="ex-01",
            title="Ascending fifths",
            tempo_bpm=100.0,
            target_key="C",
            instructions="Keep vibrato minimal.",
        ),
        notes=[
            NoteEvent(midi_note=60, duration_beats=1.0, lyric="la"),
            NoteEvent(midi_note=67, duration_beats=1.0, lyric="la"),
        ],
        output_dir=tmp_path,
        output_stem=stem,
    )


def test_fallback_render_without_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    result = render_vocal_exercise(_request(tmp_path))

    assert result.engine == "local"
    assert result.used_fallback is True
    assert result.audio_format == "wav"
    assert result.output_path.suffix == ".wav"
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 44
    assert result.metadata["renderer"] == "deterministic_local"


def test_fallback_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    first = render_vocal_exercise(_request(tmp_path, stem="take_a"))
    second = render_vocal_exercise(_request(tmp_path, stem="take_b"))

    assert first.content_sha256 == second.content_sha256
    assert first.output_path.read_bytes() == second.output_path.read_bytes()


def test_elevenlabs_path_when_key_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")

    class _FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key

        def text_to_speech(self, *args, **kwargs) -> bytes:
            return b"ID3\x04\x00\x00\x00\x00\x00\x21FAKE-MP3"

    monkeypatch.setattr("src.integrations.vocal_synthesis.ElevenLabsClient", _FakeClient)

    result = render_vocal_exercise(_request(tmp_path))

    assert result.engine == "elevenlabs"
    assert result.used_fallback is False
    assert result.audio_format == "mp3"
    assert result.output_path.suffix == ".mp3"
    assert result.output_path.exists()
    assert result.metadata["renderer"] == "elevenlabs"
