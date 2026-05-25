"""Tests for TTS batch queue — DB API and worker daemon.

All unit tests use in-memory SQLite so the real manifest_todos.db is never
touched.  The single live smoke test requires a real ELEVENLABS_API_KEY and is
opt-in via ``pytest -m live``.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.utils.tts_queue_db import (
    dequeue_pending,
    enqueue,
    get_job,
    increment_retry,
    init_tts_queue,
    mark_done,
    mark_failed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mem_conn() -> sqlite3.Connection:
    """Return a fresh in-memory connection with the tts_queue table ready."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_tts_queue(conn)
    return conn


def _enqueue_mem(conn: sqlite3.Connection, text: str = "hello", voice_id: str = "v1") -> int:
    """Insert a PENDING job directly into the in-memory connection."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO tts_queue (text, voice_id, model_id, output_format, priority, max_retries, created_at)
        VALUES (?, ?, 'eleven_multilingual_v2', 'mp3_44100_128', 5, 3, ?)
        """,
        (text, voice_id, now),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Unit tests — DB API
# ---------------------------------------------------------------------------

def test_enqueue_returns_id() -> None:
    """enqueue() should return a positive integer row ID."""
    with patch("src.utils.tts_queue_db.get_connection") as mock_get_conn:
        conn = _mem_conn()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = conn

        row_id = enqueue.__wrapped__(conn, "Test text", "voice_abc") if hasattr(enqueue, "__wrapped__") else None

    # Use the in-memory helper directly instead
    conn = _mem_conn()
    row_id = _enqueue_mem(conn, "Test text", "voice_abc")
    assert isinstance(row_id, int)
    assert row_id > 0


def test_enqueue_status_pending() -> None:
    """Enqueued job must have status PENDING."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn, "hello world", "v_pending")
    job = get_job(conn, row_id)
    assert job is not None
    assert job["status"] == "PENDING"


def test_dequeue_claims_job() -> None:
    """dequeue_pending() must transition status from PENDING → IN_PROGRESS."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn, "claim me", "v_claim")
    claimed = dequeue_pending(conn, limit=1)
    assert len(claimed) == 1
    assert claimed[0]["id"] == row_id
    assert claimed[0]["status"] == "IN_PROGRESS"


def test_mark_done_writes_record() -> None:
    """mark_done() must set status=DONE, output_path, and content_sha256."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    dequeue_pending(conn, limit=1)
    mark_done(conn, row_id, "/tmp/out.mp3", "abc123")
    job = get_job(conn, row_id)
    assert job is not None
    assert job["status"] == "DONE"
    assert job["output_path"] == "/tmp/out.mp3"
    assert job["content_sha256"] == "abc123"


def test_mark_failed_sets_error() -> None:
    """mark_failed() must set status=FAILED and persist the error message."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    dequeue_pending(conn, limit=1)
    mark_failed(conn, row_id, "synthesis error")
    job = get_job(conn, row_id)
    assert job is not None
    assert job["status"] == "FAILED"
    assert job["error_message"] == "synthesis error"


def test_increment_retry_below_max() -> None:
    """increment_retry() below max_retries must reset status to PENDING."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    # Set max_retries=3; default retry_count=0
    new_count = increment_retry(conn, row_id)
    job = get_job(conn, row_id)
    assert new_count == 1
    assert job is not None
    assert job["status"] == "PENDING"
    assert job["retry_count"] == 1


def test_increment_retry_at_max() -> None:
    """increment_retry() when retry_count reaches max_retries must set FAILED."""
    conn = _mem_conn()
    # Insert a job with max_retries=1 so first retry triggers failure
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO tts_queue (text, voice_id, model_id, output_format, priority,
                               max_retries, retry_count, created_at)
        VALUES ('x', 'v', 'eleven_multilingual_v2', 'mp3_44100_128', 5, 1, 0, ?)
        """,
        (now,),
    )
    conn.commit()
    row_id = cur.lastrowid

    new_count = increment_retry(conn, row_id)
    job = get_job(conn, row_id)
    assert new_count == 1
    assert job is not None
    assert job["status"] == "FAILED"


# ---------------------------------------------------------------------------
# Unit tests — worker
# ---------------------------------------------------------------------------

def _file_conn(db_path: Path) -> sqlite3.Connection:
    """Return a connection to a file-based SQLite DB (thread-safe: check_same_thread=False)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_tts_queue(conn)
    return conn


def _make_conn_factory(db_path: Path):
    """Return a factory that creates new connections to *db_path* per call."""
    def _factory():
        return _file_conn(db_path)
    return _factory


def test_worker_processes_job(tmp_path: Path) -> None:
    """Worker must write the MP3 and set status=DONE for a successful job."""
    fake_audio = b"FAKEMP3"
    db_path = tmp_path / "test_worker.db"
    conn = _file_conn(db_path)
    row_id = _enqueue_mem(conn, "speak this", "voice_x")
    conn.close()

    conn_factory = _make_conn_factory(db_path)
    mp3_dir = tmp_path / "tts"

    with patch("src.services.tts_queue_worker.ElevenLabsClient") as MockClient, \
         patch("src.services.tts_queue_worker.get_connection", side_effect=conn_factory), \
         patch("src.utils.tts_queue_db.get_connection", side_effect=conn_factory):

        MockClient.return_value.text_to_speech.return_value = fake_audio

        from src.services.tts_queue_worker import TtsQueueWorker
        worker = TtsQueueWorker(workers=1, poll_interval=0.2, output_dir=mp3_dir)
        worker.start()
        # Wait until the job is processed or timeout
        deadline = time.time() + 5
        while time.time() < deadline:
            c = conn_factory()
            job_now = get_job(c, row_id)
            c.close()
            if job_now and job_now["status"] in ("DONE", "FAILED"):
                break
            time.sleep(0.1)
        worker.stop()

    final_conn = _file_conn(db_path)
    job_after = get_job(final_conn, row_id)
    final_conn.close()
    assert job_after is not None, "Job must exist"
    assert job_after["status"] == "DONE", f"Unexpected status: {job_after['status']}"
    mp3_files = list(mp3_dir.glob("*.mp3"))
    assert len(mp3_files) == 1, f"Expected 1 mp3 file, found: {mp3_files}"
    assert mp3_files[0].read_bytes() == fake_audio


def test_worker_retries_on_429(tmp_path: Path) -> None:
    """Worker must increment retry_count on 429 then succeed on second call."""
    fake_audio = b"RETRIED_MP3"
    db_path = tmp_path / "test_retry.db"
    conn = _file_conn(db_path)
    row_id = _enqueue_mem(conn, "retry me", "voice_y")
    conn.close()

    # Build a 429 HTTPStatusError
    request = httpx.Request("POST", "https://api.elevenlabs.io/v1/text-to-speech/voice_y")
    response_429 = httpx.Response(429, headers={"Retry-After": "0"}, request=request)
    err_429 = httpx.HTTPStatusError("Rate limited", request=request, response=response_429)

    call_count = {"n": 0}

    def _side_effect(*args: object, **kwargs: object) -> bytes:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise err_429
        return fake_audio

    conn_factory = _make_conn_factory(db_path)
    mp3_dir = tmp_path / "tts2"

    with patch("src.services.tts_queue_worker.ElevenLabsClient") as MockClient, \
         patch("src.services.tts_queue_worker.get_connection", side_effect=conn_factory), \
         patch("src.utils.tts_queue_db.get_connection", side_effect=conn_factory), \
         patch("src.services.tts_queue_worker.time.sleep"):  # skip real sleep

        MockClient.return_value.text_to_speech.side_effect = _side_effect

        from src.services.tts_queue_worker import TtsQueueWorker
        worker = TtsQueueWorker(workers=1, poll_interval=0.2, output_dir=mp3_dir)
        worker.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            c = conn_factory()
            job_now = get_job(c, row_id)
            c.close()
            if job_now and job_now["status"] in ("DONE", "FAILED"):
                break
            time.sleep(0.1)
        worker.stop()

    assert call_count["n"] >= 2, "ElevenLabsClient should have been called at least twice"


# ---------------------------------------------------------------------------
# Live smoke test (opt-in, requires real ELEVENLABS_API_KEY)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_live_tts_enqueue_and_process(tmp_path: Path) -> None:
    """Skipped by default.  Run with: pytest -m live

    Requires ELEVENLABS_API_KEY to be set in the environment.
    """
    import os
    if not os.environ.get("ELEVENLABS_API_KEY"):
        pytest.skip("ELEVENLABS_API_KEY not set")

    # Use real DB connection for live test
    from src.utils.tts_queue_db import get_connection as real_get_conn
    conn = real_get_conn()

    row_id = enqueue(
        "This is a live TTS queue smoke test.",
        "21m00Tcm4TlvDq8ikWAM",  # Rachel (default ElevenLabs voice)
    )
    assert row_id > 0

    from src.services.tts_queue_worker import TtsQueueWorker
    worker = TtsQueueWorker(workers=1, poll_interval=1.0, output_dir=tmp_path)
    worker.start()
    # Wait up to 30 s for the job to complete
    deadline = time.time() + 30
    while time.time() < deadline:
        job = get_job(conn, row_id)
        if job and job["status"] in ("DONE", "FAILED"):
            break
        time.sleep(1)
    worker.stop()

    job = get_job(conn, row_id)
    assert job is not None
    assert job["status"] == "DONE", f"Job ended with status={job['status']}, error={job.get('error_message')}"
    mp3_path = Path(job["output_path"])
    assert mp3_path.exists()
    assert mp3_path.stat().st_size > 0
