"""Vocal synthesis seam for Music-side exercise rendering.

This module accepts structured exercise metadata + note events and returns a
stable metadata-rich result that includes a playable audio file path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import math
import os
from pathlib import Path
import struct
from typing import Any, Literal, Sequence
import wave

from src.config.elevenlabs_settings import DEFAULT_MODEL_ID, DEFAULT_OUTPUT_FORMAT
from src.integrations.elevenlabs.client import ElevenLabsClient
from src.utils.audio_output_policy import (
    atomic_write_bytes,
    resolve_audio_output_directory,
    resolve_audio_output_path,
)

_AUDIO_SAMPLE_RATE_HZ = 22050
_PCM_PEAK = 32767
_PCM_AMPLITUDE = 0.25


@dataclass(frozen=True, slots=True)
class ExerciseMetadata:
    """Exercise-level metadata required by the vocal renderer."""

    exercise_id: str
    title: str
    tempo_bpm: float
    target_key: str | None = None
    instructions: str | None = None


@dataclass(frozen=True, slots=True)
class NoteEvent:
    """Single note event in MIDI space with beat duration."""

    midi_note: int
    duration_beats: float
    lyric: str | None = None
    velocity: int = 100


@dataclass(frozen=True, slots=True)
class VocalRenderRequest:
    """Input contract for rendering a vocal exercise."""

    exercise: ExerciseMetadata
    notes: Sequence[NoteEvent]
    output_dir: Path | str
    output_stem: str
    prefer_engine: Literal["auto", "elevenlabs", "local"] = "auto"
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    model_id: str = DEFAULT_MODEL_ID


@dataclass(frozen=True, slots=True)
class VocalRenderResult:
    """Output contract returned to upstream renderers."""

    output_path: Path
    engine: Literal["elevenlabs", "local"]
    audio_format: Literal["mp3", "wav"]
    note_count: int
    duration_seconds: float
    sample_rate_hz: int
    used_fallback: bool
    content_sha256: str
    metadata: dict[str, Any]


def render_vocal_exercise(
    request: VocalRenderRequest,
    *,
    api_key: str | None = None,
    output_root: Path | str | None = None,
) -> VocalRenderResult:
    """Render an exercise as playable audio with a stable metadata result."""
    _validate_request(request)

    policy_root = (
        Path(output_root)
        if output_root is not None
        else Path(__file__).resolve().parents[2] / "output"
    )
    resolved_output_dir = resolve_audio_output_directory(policy_root, request.output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolve_audio_output_path(
        resolved_output_dir,
        f"{request.output_stem}.mp3",
        allowed_extensions=(".mp3",),
    )

    resolved_key = (api_key or os.environ.get("ELEVENLABS_API_KEY", "")).strip()
    should_try_remote = (
        request.prefer_engine in ("auto", "elevenlabs") and bool(resolved_key)
    )

    fallback_reason: str | None = None
    if should_try_remote:
        try:
            audio = _render_with_elevenlabs(request=request, api_key=resolved_key)
            output_path = resolve_audio_output_path(
                resolved_output_dir,
                f"{request.output_stem}.mp3",
                allowed_extensions=(".mp3",),
            )
            atomic_write_bytes(output_path, audio)
            duration_seconds = _duration_seconds(request.notes, request.exercise.tempo_bpm)
            sha = hashlib.sha256(audio).hexdigest()
            return VocalRenderResult(
                output_path=output_path,
                engine="elevenlabs",
                audio_format="mp3",
                note_count=len(request.notes),
                duration_seconds=duration_seconds,
                sample_rate_hz=_AUDIO_SAMPLE_RATE_HZ,
                used_fallback=False,
                content_sha256=sha,
                metadata={
                    "exercise_id": request.exercise.exercise_id,
                    "voice_id": request.voice_id,
                    "model_id": request.model_id,
                    "renderer": "elevenlabs",
                },
            )
        except Exception as exc:  # pragma: no cover - exercised in integration envs
            fallback_reason = str(exc)

    audio, duration_seconds = _render_deterministic_wave(request)
    output_path = resolve_audio_output_path(
        resolved_output_dir,
        f"{request.output_stem}.wav",
        allowed_extensions=(".wav",),
    )
    atomic_write_bytes(output_path, audio)
    sha = hashlib.sha256(audio).hexdigest()
    metadata = {
        "exercise_id": request.exercise.exercise_id,
        "renderer": "deterministic_local",
    }
    if fallback_reason:
        metadata["fallback_reason"] = fallback_reason

    return VocalRenderResult(
        output_path=output_path,
        engine="local",
        audio_format="wav",
        note_count=len(request.notes),
        duration_seconds=duration_seconds,
        sample_rate_hz=_AUDIO_SAMPLE_RATE_HZ,
        used_fallback=True,
        content_sha256=sha,
        metadata=metadata,
    )


def _render_with_elevenlabs(*, request: VocalRenderRequest, api_key: str) -> bytes:
    prompt = _build_prompt_text(request.exercise, request.notes)
    client = ElevenLabsClient(api_key=api_key)
    return client.text_to_speech(
        prompt,
        request.voice_id,
        model_id=request.model_id,
        output_format=DEFAULT_OUTPUT_FORMAT,
    )


def _render_deterministic_wave(request: VocalRenderRequest) -> tuple[bytes, float]:
    bpm = request.exercise.tempo_bpm
    sec_per_beat = 60.0 / bpm
    frames = bytearray()

    for note in request.notes:
        frequency_hz = 440.0 * (2.0 ** ((note.midi_note - 69) / 12.0))
        duration_seconds = note.duration_beats * sec_per_beat
        samples = max(1, int(duration_seconds * _AUDIO_SAMPLE_RATE_HZ))

        for idx in range(samples):
            t = idx / _AUDIO_SAMPLE_RATE_HZ
            sample = int(
                _PCM_PEAK
                * _PCM_AMPLITUDE
                * math.sin(2.0 * math.pi * frequency_hz * t)
            )
            frames.extend(struct.pack("<h", sample))

    total_duration = _duration_seconds(request.notes, bpm)
    wav_bytes = _wave_bytes_from_pcm(bytes(frames))
    return wav_bytes, total_duration


def _wave_bytes_from_pcm(pcm_bytes: bytes) -> bytes:
    buff = BytesIO()
    with wave.open(buff, "wb") as wav_handle:
        wav_handle.setnchannels(1)
        wav_handle.setsampwidth(2)
        wav_handle.setframerate(_AUDIO_SAMPLE_RATE_HZ)
        wav_handle.writeframes(pcm_bytes)
    return buff.getvalue()


def _duration_seconds(notes: Sequence[NoteEvent], tempo_bpm: float) -> float:
    total_beats = sum(note.duration_beats for note in notes)
    return total_beats * (60.0 / tempo_bpm)


def _build_prompt_text(exercise: ExerciseMetadata, notes: Sequence[NoteEvent]) -> str:
    lines = [
        f"Exercise: {exercise.title}",
        f"Tempo: {exercise.tempo_bpm:.2f} BPM",
    ]
    if exercise.target_key:
        lines.append(f"Key: {exercise.target_key}")
    if exercise.instructions:
        lines.append(f"Instructions: {exercise.instructions}")

    note_parts = []
    for note in notes:
        token = f"MIDI {note.midi_note} for {note.duration_beats:.2f} beats"
        if note.lyric:
            token += f" lyric '{note.lyric}'"
        note_parts.append(token)

    lines.append("Sequence: " + "; ".join(note_parts))
    lines.append("Sing this as a clear training guide vocal.")
    return "\n".join(lines)


def _validate_request(request: VocalRenderRequest) -> None:
    if not request.notes:
        raise ValueError("notes must contain at least one note event")
    if request.exercise.tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be greater than zero")
    if not request.output_stem.strip():
        raise ValueError("output_stem must be a non-empty string")
    if any(separator in request.output_stem for separator in ("/", "\\")):
        raise ValueError("output_stem cannot contain path separators")
    if Path(request.output_stem).suffix:
        raise ValueError("output_stem cannot contain an extension")

    for note in request.notes:
        if note.duration_beats <= 0:
            raise ValueError("each note duration_beats must be greater than zero")
        if note.midi_note < 0 or note.midi_note > 127:
            raise ValueError("midi_note must be in MIDI range 0-127")


__all__ = [
    "ExerciseMetadata",
    "NoteEvent",
    "VocalRenderRequest",
    "VocalRenderResult",
    "render_vocal_exercise",
]
