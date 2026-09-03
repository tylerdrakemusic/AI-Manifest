"""Governed, non-blocking submission boundary for overseer voice alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.utils.tts_queue_db import enqueue_on_connection_status, enqueue_with_status


@dataclass(frozen=True, slots=True)
class AlertSubmissionResult:
    """Stable result returned after an alert is accepted or rejected."""

    decision_id: str
    job_id: int | None
    accepted: bool
    deduplicated: bool = False
    error: str | None = None


def submit_alert(
    decision_id: str,
    text: str,
    *,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    priority: int = 5,
    max_retries: int = 3,
    connection_factory: Callable[[], object] | None = None,
) -> AlertSubmissionResult:
    """Queue one alert without calling ElevenLabs or mutating caller state."""
    if not decision_id.strip():
        return AlertSubmissionResult(decision_id, None, False, error="decision_id is required")
    if not text.strip():
        return AlertSubmissionResult(decision_id, None, False, error="text is required")
    if not voice_id.strip():
        return AlertSubmissionResult(decision_id, None, False, error="voice_id is required")
    try:
        if connection_factory is None:
            job_id, inserted = enqueue_with_status(
                text,
                voice_id,
                model_id=model_id,
                output_format=output_format,
                priority=priority,
                max_retries=max_retries,
                decision_id=decision_id,
            )
            deduplicated = not inserted
        else:
            conn = connection_factory()
            try:
                job_id, inserted = enqueue_on_connection_status(
                    conn,
                    text,
                    voice_id,
                    model_id=model_id,
                    output_format=output_format,
                    priority=priority,
                    max_retries=max_retries,
                    decision_id=decision_id,
                )
                deduplicated = not inserted
            finally:
                conn.close()
        return AlertSubmissionResult(decision_id, job_id, True, deduplicated=deduplicated)
    except Exception as exc:
        return AlertSubmissionResult(decision_id, None, False, error=str(exc))