"""Integration surfaces exposed by 👁AI-Manifest."""

from .vocal_synthesis import (
	ExerciseMetadata,
	NoteEvent,
	VocalRenderRequest,
	VocalRenderResult,
	render_vocal_exercise,
)

__all__ = [
	"ExerciseMetadata",
	"NoteEvent",
	"VocalRenderRequest",
	"VocalRenderResult",
	"render_vocal_exercise",
]
