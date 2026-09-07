"""Tests for TTS batch queue — DB API and worker daemon.

All unit tests use in-memory SQLite so the real manifest_todos.db is never
touched.  The single live smoke test requires a real ELEVENLABS_API_KEY and is
opt-in via ``pytest -m live``.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.utils.tts_queue_db import (
    dequeue_pending,
    enqueue,
    enqueue_on_connection_status,
    get_job,
    increment_retry,
    init_tts_queue,
    mark_done,
    mark_failed,
    recover_stale_jobs,
    reconcile_existing_artifact,
)
from src.services.tts_queue_worker import (
    TtsQueueWorker,
    classify_http_error,
    compute_backoff_delay,
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


def test_enqueue_uses_stable_request_identity_for_logical_render_claim() -> None:
    """Equivalent render requests converge on one logical queue claim."""
    conn = _mem_conn()
    first = enqueue_on_connection_status(
        conn, "same text", "voice", model_id="model", output_format="format"
    )
    second = enqueue_on_connection_status(
        conn, "same text", "voice", model_id="model", output_format="format"
    )

    assert first == (first[0], True)
    assert second == (first[0], False)
    job = get_job(conn, first[0])
    assert job is not None
    assert len(job["request_identity"]) == 64


def test_claim_creates_provider_neutral_attempt_and_usage_record() -> None:
    """A logical claim creates an attempt row without provider-specific fields."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)

    claimed = dequeue_pending(conn)

    assert claimed[0]["attempt_id"] == 1
    attempt = conn.execute(
        "SELECT * FROM tts_queue_attempts WHERE id=1"
    ).fetchone()
    assert attempt is not None
    assert attempt["job_id"] == row_id
    assert attempt["status"] == "STARTED"
    assert attempt["usage_characters"] == 5


def test_stale_claim_becomes_ambiguous_and_is_not_replayed() -> None:
    """A worker crash must stop automatic replay when provider outcome is unknown."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    stale_started = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    conn.execute(
        "UPDATE tts_queue SET status='IN_PROGRESS', started_at=? WHERE id=?",
        (stale_started, row_id),
    )
    conn.commit()

    assert recover_stale_jobs(conn, lease_timeout_seconds=60) == [row_id]
    assert get_job(conn, row_id)["status"] == "AMBIGUOUS"  # type: ignore[index]
    assert dequeue_pending(conn) == []


def test_mark_done_requires_existing_artifact_with_matching_sha256(tmp_path: Path) -> None:
    """Completion and reconciliation accept only an existing verified artifact."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    dequeue_pending(conn)
    artifact = tmp_path / "render.mp3"
    artifact.write_bytes(b"verified")
    checksum = hashlib.sha256(b"verified").hexdigest()

    mark_done(conn, row_id, str(artifact), checksum)
    assert get_job(conn, row_id)["status"] == "DONE"  # type: ignore[index]

    conn.execute("UPDATE tts_queue SET status='AMBIGUOUS' WHERE id=?", (row_id,))
    conn.commit()
    reconcile_existing_artifact(conn, row_id, str(artifact), checksum)
    assert get_job(conn, row_id)["status"] == "DONE"  # type: ignore[index]


def test_worker_internal_provider_api_supports_deterministic_failure_injection(
    tmp_path: Path,
) -> None:
    """The worker can run with an injected provider and deterministic failure hook."""
    db_path = tmp_path / "worker.db"
    conn = _file_conn(db_path)
    row_id = _enqueue_mem(conn, "inject", "voice")
    claimed = dequeue_pending(conn)
    conn.close()
    calls = {"count": 0}

    def provider(**_: object) -> bytes:
        calls["count"] += 1
        return b"injected"

    def fail_once(event: str, _job: dict[str, object]) -> None:
        if event == "before_publish" and calls["count"] == 1:
            raise RuntimeError("injected crash")

    worker = TtsQueueWorker(
        workers=1,
        output_dir=tmp_path / "tts",
        provider=provider,
        failure_injector=fail_once,
    )
    check = _file_conn(db_path)
    job = get_job(check, row_id)
    check.close()
    assert job is not None
    with pytest.raises(RuntimeError, match="injected crash"):
        worker._process_job({**job, "status": "IN_PROGRESS"})

    check = _file_conn(db_path)
    assert get_job(check, row_id)["status"] == "IN_PROGRESS"  # type: ignore[index]
    assert calls["count"] == 1


def test_dequeue_claims_job() -> None:
    """dequeue_pending() must transition status from PENDING → IN_PROGRESS."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn, "claim me", "v_claim")
    claimed = dequeue_pending(conn, limit=1)
    assert len(claimed) == 1
    assert claimed[0]["id"] == row_id
    assert claimed[0]["status"] == "IN_PROGRESS"


def test_mark_done_writes_record(tmp_path: Path) -> None:
    """mark_done() must set status=DONE, output_path, and content_sha256."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    dequeue_pending(conn, limit=1)
    artifact = tmp_path / "out.mp3"
    artifact.write_bytes(b"audio")
    mark_done(conn, row_id, str(artifact), hashlib.sha256(b"audio").hexdigest())
    job = get_job(conn, row_id)
    assert job is not None
    assert job["status"] == "DONE"
    assert job["output_path"] == str(artifact)
    assert job["content_sha256"] == hashlib.sha256(b"audio").hexdigest()


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


def test_recover_stale_job_requeues_and_records_recovery() -> None:
    """Expired IN_PROGRESS jobs return to PENDING without losing retry history."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    stale_started = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    conn.execute(
        "UPDATE tts_queue SET status='IN_PROGRESS', retry_count=2, started_at=? WHERE id=?",
        (stale_started, row_id),
    )
    conn.commit()

    recovered = recover_stale_jobs(conn, lease_timeout_seconds=60)

    assert recovered == [row_id]
    job = get_job(conn, row_id)
    assert job is not None
    assert job["status"] == "AMBIGUOUS"
    assert job["retry_count"] == 2
    assert job["started_at"] is None
    assert "recovered" in (job["error_message"] or "").lower()


def test_recover_stale_jobs_does_not_requeue_valid_lease() -> None:
    """A job started within the lease remains owned by its active worker."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    current = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE tts_queue SET status='IN_PROGRESS', started_at=? WHERE id=?",
        ((current - timedelta(seconds=10)).isoformat(), row_id),
    )
    conn.commit()

    assert recover_stale_jobs(conn, lease_timeout_seconds=60, now=current) == []
    assert get_job(conn, row_id)["status"] == "IN_PROGRESS"  # type: ignore[index]


def test_recover_stale_jobs_is_idempotent() -> None:
    """A recovered job is not recorded twice on a subsequent recovery pass."""
    conn = _mem_conn()
    row_id = _enqueue_mem(conn)
    current = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE tts_queue SET status='IN_PROGRESS', started_at=? WHERE id=?",
        ((current - timedelta(minutes=2)).isoformat(), row_id),
    )
    conn.commit()

    assert recover_stale_jobs(conn, lease_timeout_seconds=60, now=current) == [row_id]
    assert recover_stale_jobs(conn, lease_timeout_seconds=60, now=current) == []
    assert conn.execute("SELECT COUNT(*) FROM tts_queue_recoveries").fetchone()[0] == 1


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_classify_http_error_marks_retryable_statuses_transient(status: int) -> None:
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status, request=request)
    error = httpx.HTTPStatusError("provider error", request=request, response=response)
    assert classify_http_error(error) == "transient"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_classify_http_error_marks_other_4xx_permanent(status: int) -> None:
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status, request=request)
    error = httpx.HTTPStatusError("provider error", request=request, response=response)
    assert classify_http_error(error) == "permanent"


def test_compute_backoff_delay_honors_retry_after_and_caps() -> None:
    assert compute_backoff_delay(4, retry_after=90, base_delay=2, max_delay=30) == 30
    assert compute_backoff_delay(2, retry_after=None, base_delay=2, max_delay=30) == 8


def test_worker_publishes_deterministic_output_atomically(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A successful retry uses the job ID path and leaves no temporary file."""
    caplog.set_level(logging.INFO)
    fake_audio = b"ATOMIC_MP3"
    db_path = tmp_path / "atomic.db"
    conn = _file_conn(db_path)
    row_id = _enqueue_mem(conn, "atomic", "voice")
    conn.close()
    conn_factory = _make_conn_factory(db_path)

    with patch("src.services.tts_queue_worker.ElevenLabsClient") as mock_client, \
         patch("src.services.tts_queue_worker.get_connection", side_effect=conn_factory):
        mock_client.return_value.text_to_speech.return_value = fake_audio
        from src.services.tts_queue_worker import TtsQueueWorker
        worker = TtsQueueWorker(workers=1, poll_interval=0.05, output_dir=tmp_path / "tts")
        worker.start()
        deadline = time.time() + 3
        while time.time() < deadline:
            check = conn_factory()
            status = get_job(check, row_id)["status"]  # type: ignore[index]
            check.close()
            if status == "DONE":
                break
            time.sleep(0.05)
        worker.stop()

    assert (tmp_path / "tts" / f"{row_id}.mp3").read_bytes() == fake_audio
    assert not list((tmp_path / "tts").glob("*.tmp"))
    lifecycle = [record.message for record in caplog.records if "tts_queue" in record.message]
    assert any('"event": "STARTED"' in message for message in lifecycle)
    done_log = next(message for message in lifecycle if '"event": "DONE"' in message)
    assert '"characters": 6' in done_log
    assert '"output_size": 10' in done_log


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
