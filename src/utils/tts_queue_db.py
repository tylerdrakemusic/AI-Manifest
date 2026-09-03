"""TTS queue DB — schema + Python API for the ElevenLabs batch queue.

Adds ``tts_queue`` table to the existing manifest_todos.db.  All functions
accept an explicit ``sqlite3.Connection`` except the top-level convenience
helpers (``get_connection`` / ``enqueue``) which open their own connection.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "manifest_todos.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tts_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    text           TEXT NOT NULL,
    voice_id       TEXT NOT NULL,
    model_id       TEXT NOT NULL DEFAULT 'eleven_multilingual_v2',
    output_format  TEXT NOT NULL DEFAULT 'mp3_44100_128',
    priority       INTEGER NOT NULL DEFAULT 5,
    status         TEXT NOT NULL DEFAULT 'PENDING'
                       CHECK(status IN ('PENDING','IN_PROGRESS','DONE','FAILED')),
    retry_count    INTEGER NOT NULL DEFAULT 0,
    max_retries    INTEGER NOT NULL DEFAULT 3,
    output_path    TEXT,
    content_sha256 TEXT,
    error_message  TEXT,
    created_at     TEXT NOT NULL,
    started_at     TEXT,
    completed_at   TEXT
)
"""

_CREATE_RECOVERY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tts_queue_recoveries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id             INTEGER NOT NULL,
    recovered_at       TEXT NOT NULL,
    previous_started_at TEXT,
    retry_count        INTEGER NOT NULL,
    reason             TEXT NOT NULL
)
"""


def init_tts_queue(conn: sqlite3.Connection) -> None:
    """Create the tts_queue table if it does not exist (idempotent)."""
    conn.execute(_CREATE_TABLE_SQL)
    conn.execute(_CREATE_RECOVERY_TABLE_SQL)
    conn.commit()


def get_connection() -> sqlite3.Connection:
    """Return a WAL-mode connection to manifest_todos.db."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_tts_queue(conn)
    return conn


def enqueue(
    text: str,
    voice_id: str,
    *,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    priority: int = 5,
    max_retries: int = 3,
) -> int:
    """Insert a PENDING job and return its row ID."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO tts_queue
                (text, voice_id, model_id, output_format, priority, max_retries, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (text, voice_id, model_id, output_format, priority, max_retries, now),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def dequeue_pending(conn: sqlite3.Connection, limit: int = 1) -> list[dict[str, Any]]:
    """Atomically claim up to *limit* PENDING jobs → IN_PROGRESS.

    Returns the claimed rows as plain dicts.
    """
    now = datetime.now(timezone.utc).isoformat()
    # Fetch candidate IDs first, then UPDATE — SQLite does not support
    # UPDATE … RETURNING in older versions, but this two-step approach is
    # safe under WAL when running inside a single connection.
    rows = conn.execute(
        """
        SELECT id FROM tts_queue
        WHERE status = 'PENDING'
        ORDER BY priority ASC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if not rows:
        return []

    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE tts_queue SET status='IN_PROGRESS', started_at=? WHERE id IN ({placeholders})",  # nosec B608 — placeholders are ?-bound params; ids are ints from SELECT
        [now, *ids],
    )
    conn.commit()

    claimed = conn.execute(
        f"SELECT * FROM tts_queue WHERE id IN ({placeholders})",  # nosec B608
        ids,
    ).fetchall()
    return [dict(r) for r in claimed]


def mark_done(
    conn: sqlite3.Connection,
    job_id: int,
    output_path: str,
    content_sha256: str,
) -> None:
    """Mark a job as DONE with its output path and SHA-256 checksum."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE tts_queue
        SET status='DONE', output_path=?, content_sha256=?, completed_at=?
        WHERE id=?
        """,
        (output_path, content_sha256, now, job_id),
    )
    conn.commit()


def mark_failed(
    conn: sqlite3.Connection,
    job_id: int,
    error_message: str,
) -> None:
    """Mark a job as FAILED with an error message."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE tts_queue
        SET status='FAILED', error_message=?, completed_at=?
        WHERE id=?
        """,
        (error_message, now, job_id),
    )
    conn.commit()


def increment_retry(conn: sqlite3.Connection, job_id: int) -> int:
    """Bump retry_count by 1.

    If the new count is less than max_retries the status is reset to PENDING
    so the job can be picked up again.  Otherwise the job is marked FAILED.

    Returns the new retry_count.
    """
    row = conn.execute(
        "SELECT retry_count, max_retries FROM tts_queue WHERE id=?", (job_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"No tts_queue row with id={job_id}")

    new_count = row["retry_count"] + 1
    if new_count < row["max_retries"]:
        conn.execute(
            "UPDATE tts_queue SET retry_count=?, status='PENDING' WHERE id=?",
            (new_count, job_id),
        )
    else:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE tts_queue SET retry_count=?, status='FAILED', completed_at=? WHERE id=?",
            (new_count, now, job_id),
        )
    conn.commit()
    return new_count


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    """Return a single job row as a dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM tts_queue WHERE id=?", (job_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def recover_stale_jobs(
    conn: sqlite3.Connection,
    *,
    lease_timeout_seconds: float,
    now: datetime | None = None,
) -> list[int]:
    """Requeue expired ``IN_PROGRESS`` jobs and record each recovery.

    Recovery is idempotent for a given observation because the status update
    and recovery insert happen in one transaction.  Retry counts are retained.
    """
    if lease_timeout_seconds < 0:
        raise ValueError("lease_timeout_seconds must be non-negative")
    recovery_time = now or datetime.now(timezone.utc)
    cutoff = recovery_time.timestamp() - lease_timeout_seconds
    rows = conn.execute(
        "SELECT id, started_at, retry_count FROM tts_queue "
        "WHERE status='IN_PROGRESS' AND started_at IS NOT NULL"
    ).fetchall()
    stale = []
    for row in rows:
        try:
            started_timestamp = datetime.fromisoformat(row["started_at"]).timestamp()
        except (TypeError, ValueError):
            continue
        if started_timestamp <= cutoff:
            stale.append(row)

    if not stale:
        return []

    reason = f"Recovered orphaned job after {lease_timeout_seconds:g}s lease timeout"
    recovered_at = recovery_time.isoformat()
    for row in stale:
        conn.execute(
            "UPDATE tts_queue SET status='PENDING', started_at=NULL, "
            "error_message=? WHERE id=? AND status='IN_PROGRESS'",
            (reason, row["id"]),
        )
        conn.execute(
            "INSERT INTO tts_queue_recoveries "
            "(job_id, recovered_at, previous_started_at, retry_count, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (row["id"], recovered_at, row["started_at"], row["retry_count"], reason),
        )
    conn.commit()
    return [row["id"] for row in stale]
