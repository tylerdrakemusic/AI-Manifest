# Vocal Synthesis Contract (FR-20260511-vocal-pilot-mp3-training)

This module provides the AI-Manifest renderer seam that Music can call directly
(or mirror in Music-side adapters if cross-repo imports are not used).

## Module

- `src.integrations.vocal_synthesis`
- Main entry point: `render_vocal_exercise(request, api_key=None)`

## Input Contract

- `ExerciseMetadata`
- `NoteEvent`
- `VocalRenderRequest`

```python
from src.integrations.vocal_synthesis import (
    ExerciseMetadata,
    NoteEvent,
    VocalRenderRequest,
    render_vocal_exercise,
)

request = VocalRenderRequest(
    exercise=ExerciseMetadata(
        exercise_id="ex-01",
        title="Ascending fifths",
        tempo_bpm=100.0,
        target_key="C",
        instructions="Keep tone bright.",
    ),
    notes=[
        NoteEvent(midi_note=60, duration_beats=1.0, lyric="la"),
        NoteEvent(midi_note=67, duration_beats=1.0, lyric="la"),
    ],
    output_dir="output/tts",
    output_stem="exercise_take_01",
)

result = render_vocal_exercise(request)
```

## Output Contract

`VocalRenderResult` fields:

- `output_path: Path` — generated playable file path
- `engine: Literal["elevenlabs", "local"]`
- `audio_format: Literal["mp3", "wav"]`
- `note_count: int`
- `duration_seconds: float`
- `sample_rate_hz: int`
- `used_fallback: bool`
- `content_sha256: str`
- `metadata: dict[str, Any]`

## Engine Behavior

- If `ELEVENLABS_API_KEY` is present (or `api_key` provided), module attempts ElevenLabs synthesis and writes `<output_stem>.mp3`.
- If key is absent, or remote synthesis fails, module performs deterministic local waveform synthesis and writes `<output_stem>.wav`.
- Deterministic fallback guarantees stable CI/test output bytes for equivalent input.
