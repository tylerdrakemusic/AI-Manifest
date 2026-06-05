"""Focused tests for the vocal synthesis renderer seam contract."""

from __future__ import annotations

from hashlib import sha256
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


def _assert_contract_compliance(result, expected_engine: str, expected_audio_format: str, expected_renderer: str, expected_used_fallback: bool) -> None:
    assert result.engine == expected_engine
    assert result.audio_format == expected_audio_format
    assert result.output_path.exists()
    assert result.note_count == 2
    assert result.sample_rate_hz == 22050
    assert result.duration_seconds == pytest.approx(1.20, abs=0.001)
    assert result.used_fallback is expected_used_fallback
    assert result.content_sha256 == sha256(result.output_path.read_bytes()).hexdigest()
    assert result.metadata["exercise_id"] == "ex-01"
    assert result.metadata["renderer"] == expected_renderer


def test_fallback_render_without_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    result = render_vocal_exercise(_request(tmp_path))

    _assert_contract_compliance(
        result,
        expected_engine="local",
        expected_audio_format="wav",
        expected_renderer="deterministic_local",
        expected_used_fallback=True,
    )


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

    _assert_contract_compliance(
        result,
        expected_engine="elevenlabs",
        expected_audio_format="mp3",
        expected_renderer="elevenlabs",
        expected_used_fallback=False,
    )


def test_elevenlabs_failure_falls_back_to_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")

    class _BrokenClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key

        def text_to_speech(self, *args, **kwargs) -> bytes:
            raise RuntimeError("remote service unavailable")

    monkeypatch.setattr("src.integrations.vocal_synthesis.ElevenLabsClient", _BrokenClient)

    result = render_vocal_exercise(_request(tmp_path))

    _assert_contract_compliance(
        result,
        expected_engine="local",
        expected_audio_format="wav",
        expected_renderer="deterministic_local",
        expected_used_fallback=True,
    )
    assert result.metadata["fallback_reason"] == "remote service unavailable"
