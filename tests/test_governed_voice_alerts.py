"""Tests for the governed asynchronous overseer voice-alert boundary."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from src.services.governed_voice_alerts import submit_alert
from src.services.tts_queue_worker import TtsQueueWorker
from src.utils.tts_queue_db import get_job, init_tts_queue


def _connection_factory(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    init_tts_queue(conn)
    return conn


def test_concurrent_submissions_for_one_decision_create_one_queue_job(
    tmp_path: Path,
) -> None:
    """A stable decision ID deduplicates concurrent alert submissions."""
    db_path = tmp_path / "alerts.db"
    initial_conn = _connection_factory(db_path)
    initial_conn.close()

    def submit() -> object:
        return submit_alert(
            "decision-42",
            "Review the quantum scheduler decision",
            voice_id="voice-1",
            connection_factory=lambda: _connection_factory(db_path),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: submit(), range(8)))

    job_ids = {result.job_id for result in results}
    assert len(job_ids) == 1
    assert all(result.accepted for result in results)
    assert any(result.deduplicated for result in results)

    conn = _connection_factory(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM tts_queue").fetchone()[0] == 1
        job = get_job(conn, next(iter(job_ids)))
        assert job is not None
        assert job["decision_id"] == "decision-42"
    finally:
        conn.close()


def test_invalid_submission_returns_failure_without_provider_call(tmp_path: Path) -> None:
    """Invalid alert input is an explicit rejection and never reaches the provider."""
    with patch("src.services.governed_voice_alerts.enqueue_with_status") as enqueue_call:
        result = submit_alert(
            "",
            "should not synthesize",
            voice_id="voice-1",
            connection_factory=lambda: _connection_factory(tmp_path / "alerts.db"),
        )

    assert result.accepted is False
    assert result.job_id is None
    assert result.error == "decision_id is required"
    enqueue_call.assert_not_called()


def test_worker_plays_successful_audio_through_injected_boundary(tmp_path: Path) -> None:
    """A completed queue job is handed to the injected playback function."""
    db_path = tmp_path / "alerts.db"
    conn = _connection_factory(db_path)
    result = submit_alert(
        "decision-1",
        "announce this",
        voice_id="voice-1",
        connection_factory=lambda: _connection_factory(db_path),
    )
    job = get_job(conn, result.job_id)
    conn.close()
    assert job is not None
    played: list[Path] = []

    with patch("src.services.tts_queue_worker.ElevenLabsClient") as client, patch(
        "src.services.tts_queue_worker.get_connection",
        side_effect=lambda: _connection_factory(db_path),
    ):
        client.return_value.text_to_speech.return_value = b"MP3"
        worker = TtsQueueWorker(
            workers=1,
            output_dir=tmp_path / "tts",
            playback=lambda path: played.append(path),
        )
        worker._process_job({**job, "status": "IN_PROGRESS"})

    assert played == [tmp_path / "tts" / f"{result.job_id}.mp3"]
    conn = _connection_factory(db_path)
    try:
        assert get_job(conn, result.job_id)["status"] == "DONE"  # type: ignore[index]
    finally:
        conn.close()


def test_worker_reports_playback_failure_as_explicit_queue_failure(tmp_path: Path) -> None:
    """A local playback error is persisted as a clear FAILED queue result."""
    db_path = tmp_path / "alerts.db"
    conn = _connection_factory(db_path)
    result = submit_alert(
        "decision-2",
        "announce failure",
        voice_id="voice-1",
        connection_factory=lambda: _connection_factory(db_path),
    )
    job = get_job(conn, result.job_id)
    conn.close()

    def fail_playback(_: Path) -> None:
        raise OSError("speaker unavailable")

    with patch("src.services.tts_queue_worker.ElevenLabsClient") as client, patch(
        "src.services.tts_queue_worker.get_connection",
        side_effect=lambda: _connection_factory(db_path),
    ):
        client.return_value.text_to_speech.return_value = b"MP3"
        worker = TtsQueueWorker(workers=1, output_dir=tmp_path / "tts", playback=fail_playback)
        worker._process_job({**job, "status": "IN_PROGRESS"})

    conn = _connection_factory(db_path)
    try:
        failed_job = get_job(conn, result.job_id)
        assert failed_job is not None
        assert failed_job["status"] == "FAILED"
        assert "speaker unavailable" in failed_job["error_message"]
    finally:
        conn.close()