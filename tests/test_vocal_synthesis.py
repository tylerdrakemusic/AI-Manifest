"""Focused tests for the vocal synthesis renderer seam contract."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import wave

import pytest

from src.config.elevenlabs_settings import DEFAULT_OUTPUT_FORMAT
from src.integrations.vocal_synthesis import (
    ExerciseMetadata,
    NoteEvent,
    VocalRenderRequest,
    VocalRenderResult,
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


def _assert_vocal_render_result_contract(
    result: VocalRenderResult, request: VocalRenderRequest
) -> bytes:
    audio_bytes = result.output_path.read_bytes()
    expected_duration = sum(note.duration_beats for note in request.notes) * (
        60.0 / request.exercise.tempo_bpm
    )

    assert result.output_path.exists()
    assert result.note_count == len(request.notes)
    assert result.duration_seconds == pytest.approx(expected_duration)
    assert result.sample_rate_hz > 0
    assert result.content_sha256 == hashlib.sha256(audio_bytes).hexdigest()
    assert result.metadata["exercise_id"] == request.exercise.exercise_id

    return audio_bytes


def test_fallback_render_without_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    request = _request(tmp_path)
    result = render_vocal_exercise(request)
    audio_bytes = _assert_vocal_render_result_contract(result, request)

    assert result.engine == "local"
    assert result.used_fallback is True
    assert result.audio_format == "wav"
    assert result.output_path.suffix == ".wav"
    assert result.metadata["renderer"] == "deterministic_local"
    with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == result.sample_rate_hz
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2


def test_fallback_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    first = render_vocal_exercise(_request(tmp_path, stem="take_a"))
    second = render_vocal_exercise(_request(tmp_path, stem="take_b"))

    assert first.content_sha256 == second.content_sha256
    assert first.output_path.read_bytes() == second.output_path.read_bytes()


def test_fallback_preserves_contract_when_remote_render_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")

    class _FailingClient:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key

        def text_to_speech(self, text: str, voice_id: str, **kwargs) -> bytes:
            raise RuntimeError("synthetic ElevenLabs failure")

    monkeypatch.setattr(
        "src.integrations.vocal_synthesis.ElevenLabsClient", _FailingClient
    )

    request = _request(tmp_path, stem="failed_remote_take")
    result = render_vocal_exercise(request)
    audio_bytes = _assert_vocal_render_result_contract(result, request)

    assert result.engine == "local"
    assert result.used_fallback is True
    assert result.audio_format == "wav"
    assert result.output_path.suffix == ".wav"
    assert result.metadata["renderer"] == "deterministic_local"
    assert result.metadata["fallback_reason"] == "synthetic ElevenLabs failure"
    with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
        assert wav_file.getframerate() == result.sample_rate_hz


def test_elevenlabs_path_when_key_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            captured["api_key"] = api_key

        def text_to_speech(self, text: str, voice_id: str, **kwargs) -> bytes:
            captured["text"] = text
            captured["voice_id"] = voice_id
            captured["kwargs"] = kwargs
            return b"ID3\x04\x00\x00\x00\x00\x00\x21FAKE-MP3"

    monkeypatch.setattr("src.integrations.vocal_synthesis.ElevenLabsClient", _FakeClient)

    request = _request(tmp_path)
    result = render_vocal_exercise(request)
    audio_bytes = _assert_vocal_render_result_contract(result, request)

    assert result.engine == "elevenlabs"
    assert result.used_fallback is False
    assert result.audio_format == "mp3"
    assert result.output_path.suffix == ".mp3"
    assert result.metadata["renderer"] == "elevenlabs"
    assert result.metadata["voice_id"] == request.voice_id
    assert result.metadata["model_id"] == request.model_id
    assert audio_bytes.startswith(b"ID3")
    assert captured["api_key"] == "fake-key"
    assert captured["voice_id"] == request.voice_id
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["model_id"] == request.model_id
    assert kwargs["output_format"] == DEFAULT_OUTPUT_FORMAT
    prompt_text = captured["text"]
    assert isinstance(prompt_text, str)
    assert request.exercise.title in prompt_text
    assert "Tempo:" in prompt_text
    assert str(int(request.exercise.tempo_bpm)) in prompt_text
    assert "BPM" in prompt_text
    assert request.exercise.target_key in prompt_text
    assert request.exercise.instructions in prompt_text
    assert "training guide vocal" in prompt_text
    for note in request.notes:
        assert f"MIDI {note.midi_note}" in prompt_text
        assert note.lyric in prompt_text
