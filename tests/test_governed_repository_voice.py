"""Tests for the governed asynchronous overseer repository-voice boundary."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.services.governed_repository_voice import submit_repository_voice
from src.services.governed_voice_alerts import submit_alert
from src.services import tts_queue_worker
from src.services.tts_queue_worker import TtsQueueWorker
from src.utils.tts_queue_db import get_job, init_tts_queue


def _connection_factory(db_path: Path, *, initialize: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    if initialize:
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
        return submit_repository_voice(
            "decision-42",
            "Review the quantum scheduler decision",
            voice_id="voice-1",
            connection_factory=lambda: _connection_factory(db_path, initialize=False),
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
    """Invalid repository-voice input is rejected before queueing."""
    with patch("src.services.governed_repository_voice.enqueue_with_status") as enqueue_call:
        result = submit_repository_voice(
            "",
            "should not synthesize",
            voice_id="voice-1",
            connection_factory=lambda: _connection_factory(tmp_path / "alerts.db"),
        )

    assert result.accepted is False
    assert result.job_id is None
    assert result.error == "decision_id is required"
    enqueue_call.assert_not_called()


def test_legacy_alert_api_remains_an_alias_for_repository_voice() -> None:
    """Keep existing consumers on the same governed repository-voice boundary."""
    assert submit_alert is submit_repository_voice


def test_worker_plays_successful_audio_through_injected_boundary(tmp_path: Path) -> None:
    """A completed queue job is handed to the injected playback function."""
    db_path = tmp_path / "alerts.db"
    conn = _connection_factory(db_path)
    result = submit_repository_voice(
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


def test_worker_reports_playback_failure_without_changing_completed_queue_result(tmp_path: Path) -> None:
    """A local playback error does not override a completed queue result."""
    db_path = tmp_path / "alerts.db"
    conn = _connection_factory(db_path)
    result = submit_repository_voice(
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
        assert failed_job["status"] == "DONE"
    finally:
        conn.close()


def test_windows_playback_uses_background_native_multimedia_without_startfile(
    monkeypatch, tmp_path: Path
) -> None:
    """Windows playback uses winmm asynchronously and never launches an app."""
    commands: list[str] = []

    class FakeWinmm:
        def mciSendStringW(self, command, *_args):
            commands.append(command)
            return 0

    monkeypatch.setattr(tts_queue_worker, "IS_WINDOWS_PLATFORM", True)
    monkeypatch.setattr(
        tts_queue_worker,
        "ctypes",
        SimpleNamespace(
            windll=SimpleNamespace(winmm=FakeWinmm()),
            create_unicode_buffer=lambda size: ["\0"] * size,
        ),
    )
    monkeypatch.setattr(
        tts_queue_worker.os,
        "startfile",
        lambda *_args: (_ for _ in ()).throw(AssertionError()),
        raising=False,
    )

    audio_path = tmp_path / "decision.mp3"
    audio_path.write_bytes(b"MP3")
    tts_queue_worker.windows_playback(audio_path)

    assert commands[0].startswith('open "')
    assert "type mpegvideo alias" in commands[0]
    assert commands[1].startswith("play repository_voice_")


def test_worker_keeps_completed_job_done_when_background_playback_fails(tmp_path: Path) -> None:
    """Playback errors are diagnostics only after synthesis and persistence succeed."""
    db_path = tmp_path / "alerts.db"
    conn = _connection_factory(db_path)
    result = submit_repository_voice(
        "decision-3",
        "announce without blocking",
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
        completed_job = get_job(conn, result.job_id)
        assert completed_job is not None
        assert completed_job["status"] == "DONE"
    finally:
        conn.close()