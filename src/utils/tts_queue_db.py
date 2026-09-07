"""TTS queue DB — schema + Python API for the ElevenLabs batch queue.

Adds ``tts_queue`` table to the existing manifest_todos.db.  All functions
accept an explicit ``sqlite3.Connection`` except the top-level convenience
helpers (``get_connection`` / ``enqueue``) which open their own connection.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "manifest_todos.db"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tts_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    text           TEXT NOT NULL,
    voice_id       TEXT NOT NULL,
    model_id       TEXT NOT NULL DEFAULT 'eleven_multilingual_v2',
    output_format  TEXT NOT NULL DEFAULT 'mp3_44100_128',
    priority       INTEGER NOT NULL DEFAULT 5,
    status         TEXT NOT NULL DEFAULT 'PENDING'
                       CHECK(status IN ('PENDING','IN_PROGRESS','DONE','FAILED','AMBIGUOUS')),
    retry_count    INTEGER NOT NULL DEFAULT 0,
    max_retries    INTEGER NOT NULL DEFAULT 3,
    output_path    TEXT,
    content_sha256 TEXT,
    error_message  TEXT,
    created_at     TEXT NOT NULL,
    started_at     TEXT,
    completed_at   TEXT,
    request_identity TEXT,
    publication_state TEXT NOT NULL DEFAULT 'UNPUBLISHED'
)
"""

_CREATE_ATTEMPTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tts_queue_attempts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id             INTEGER NOT NULL,
    attempt_number     INTEGER NOT NULL,
    request_identity   TEXT NOT NULL,
    provider_name      TEXT,
    provider_request_id TEXT,
    status             TEXT NOT NULL CHECK(status IN ('STARTED','SUCCEEDED','FAILED','AMBIGUOUS')),
    usage_characters   INTEGER NOT NULL,
    usage_units        REAL,
    usage_json         TEXT,
    error_message      TEXT,
    started_at         TEXT NOT NULL,
    completed_at       TEXT
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

_CREATE_DECISION_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_tts_queue_decision_id
ON tts_queue(decision_id)
WHERE decision_id IS NOT NULL
"""

_CREATE_REQUEST_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_tts_queue_request_identity
ON tts_queue(request_identity)
WHERE request_identity IS NOT NULL
"""


def request_identity(
    text: str, voice_id: str, model_id: str, output_format: str
) -> str:
    """Return the stable identity of one logical render request."""
    payload = json.dumps(
        {"model_id": model_id, "output_format": output_format, "text": text, "voice_id": voice_id},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def init_tts_queue(conn: sqlite3.Connection) -> None:
    """Create the tts_queue table if it does not exist (idempotent)."""
    conn.execute(_CREATE_TABLE_SQL)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tts_queue)")}
    if "decision_id" not in columns:
        conn.execute("ALTER TABLE tts_queue ADD COLUMN decision_id TEXT")
    if "request_identity" not in columns:
        conn.execute("ALTER TABLE tts_queue ADD COLUMN request_identity TEXT")
    if "publication_state" not in columns:
        conn.execute(
            "ALTER TABLE tts_queue ADD COLUMN publication_state TEXT NOT NULL DEFAULT 'UNPUBLISHED'"
        )
    legacy_rows = conn.execute(
        "SELECT id, text, voice_id, model_id, output_format FROM tts_queue "
        "WHERE request_identity IS NULL"
    ).fetchall()
    for row in legacy_rows:
        conn.execute(
            "UPDATE tts_queue SET request_identity=? WHERE id=?",
            (request_identity(row["text"], row["voice_id"], row["model_id"], row["output_format"]), row["id"]),
        )
    conn.execute(_CREATE_ATTEMPTS_TABLE_SQL)
    conn.execute(_CREATE_RECOVERY_TABLE_SQL)
    conn.execute(_CREATE_DECISION_INDEX_SQL)
    conn.execute(_CREATE_REQUEST_INDEX_SQL)
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
    decision_id: str | None = None,
) -> int:
    """Insert a PENDING job and return its row ID, deduplicating by decision ID."""
    with get_connection() as conn:
        job_id, _ = enqueue_on_connection_status(
            conn,
            text,
            voice_id,
            model_id=model_id,
            output_format=output_format,
            priority=priority,
            max_retries=max_retries,
            decision_id=decision_id,
        )
        return job_id


def enqueue_with_status(
    text: str,
    voice_id: str,
    *,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    priority: int = 5,
    max_retries: int = 3,
    decision_id: str | None = None,
) -> tuple[int, bool]:
    """Insert a job and return ``(job_id, inserted)`` using the default DB."""
    with get_connection() as conn:
        return enqueue_on_connection_status(
            conn,
            text,
            voice_id,
            model_id=model_id,
            output_format=output_format,
            priority=priority,
            max_retries=max_retries,
            decision_id=decision_id,
        )


def enqueue_on_connection(
    conn: sqlite3.Connection,
    text: str,
    voice_id: str,
    *,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    priority: int = 5,
    max_retries: int = 3,
    decision_id: str | None = None,
) -> int:
    """Insert a queue job on an explicit connection with decision deduplication."""
    job_id, _ = enqueue_on_connection_status(
        conn,
        text,
        voice_id,
        model_id=model_id,
        output_format=output_format,
        priority=priority,
        max_retries=max_retries,
        decision_id=decision_id,
    )
    return job_id


def enqueue_on_connection_status(
    conn: sqlite3.Connection,
    text: str,
    voice_id: str,
    *,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    priority: int = 5,
    max_retries: int = 3,
    decision_id: str | None = None,
) -> tuple[int, bool]:
    """Insert a job and return ``(job_id, inserted)`` atomically."""
    now = datetime.now(timezone.utc).isoformat()
    identity = request_identity(text, voice_id, model_id, output_format)
    cur = conn.execute(
        """
        INSERT INTO tts_queue
            (text, voice_id, model_id, output_format, priority, max_retries, created_at,
               decision_id, request_identity)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        (text, voice_id, model_id, output_format, priority, max_retries, now, decision_id, identity),
    )
    conn.commit()
    if cur.rowcount == 1 and cur.lastrowid:
        return int(cur.lastrowid), True
    row = conn.execute(
        "SELECT id FROM tts_queue WHERE decision_id=? OR request_identity=?",
        (decision_id, identity),
    ).fetchone()
    if row is None:
        raise RuntimeError("queue insert was ignored without an existing decision")
    return int(row[0]), False


def dequeue_pending(conn: sqlite3.Connection, limit: int = 1) -> list[dict[str, Any]]:
    """Atomically claim up to *limit* PENDING jobs → IN_PROGRESS.

    Returns the claimed rows as plain dicts.
    """
    now = datetime.now(timezone.utc).isoformat()
    # Fetch candidate IDs first, then UPDATE — SQLite does not support
    # UPDATE … RETURNING in older versions, but this two-step approach is
    # safe under WAL when running inside a single connection.
    conn.execute("BEGIN IMMEDIATE")
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
        conn.commit()
        return []

    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE tts_queue SET status='IN_PROGRESS', started_at=?, publication_state='UNPUBLISHED' WHERE id IN ({placeholders})",  # nosec B608
        [now, *ids],
    )
    attempt_ids: dict[int, int] = {}
    for job_id in ids:
        job = conn.execute("SELECT * FROM tts_queue WHERE id=?", (job_id,)).fetchone()
        if job is None:
            continue
        identity = job["request_identity"] or request_identity(
            job["text"], job["voice_id"], job["model_id"], job["output_format"]
        )
        conn.execute("UPDATE tts_queue SET request_identity=? WHERE id=?", (identity, job_id))
        attempt_number = conn.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM tts_queue_attempts WHERE job_id=?",
            (job_id,),
        ).fetchone()[0]
        attempt = conn.execute(
            "INSERT INTO tts_queue_attempts "
            "(job_id, attempt_number, request_identity, status, usage_characters, started_at) "
            "VALUES (?, ?, ?, 'STARTED', ?, ?)",
            (job_id, attempt_number, identity, len(job["text"]), now),
        )
        attempt_ids[job_id] = int(attempt.lastrowid)
    conn.commit()

    claimed = conn.execute(
        f"SELECT * FROM tts_queue WHERE id IN ({placeholders})",  # nosec B608
        ids,
    ).fetchall()
    result = []
    for row in claimed:
        item = dict(row)
        item["attempt_id"] = attempt_ids.get(item["id"])
        result.append(item)
    return result


def mark_done(
    conn: sqlite3.Connection,
    job_id: int,
    output_path: str,
    content_sha256: str,
) -> None:
    """Mark a job as DONE only after validating the published artifact."""
    if not _SHA256_RE.fullmatch(content_sha256):
        raise ValueError("content_sha256 must be a lowercase SHA-256 digest")
    artifact = Path(output_path)
    if not artifact.is_file():
        raise FileNotFoundError(output_path)
    actual_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual_sha256 != content_sha256:
        raise ValueError("artifact checksum does not match content_sha256")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE tts_queue
        SET status='DONE', output_path=?, content_sha256=?, publication_state='VERIFIED', completed_at=?
        WHERE id=?
        """,
        (output_path, content_sha256, now, job_id),
    )
    attempt = conn.execute(
        "SELECT id FROM tts_queue_attempts WHERE job_id=? AND status='STARTED' "
        "ORDER BY id DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    if attempt is not None:
        conn.execute(
            "UPDATE tts_queue_attempts SET status='SUCCEEDED', completed_at=? WHERE id=?",
            (now, attempt["id"]),
        )
    conn.commit()


def reconcile_existing_artifact(
    conn: sqlite3.Connection, job_id: int, output_path: str, content_sha256: str
) -> None:
    """Complete an ambiguous job only when an existing artifact verifies."""
    job = get_job(conn, job_id)
    if job is None:
        raise ValueError(f"No tts_queue row with id={job_id}")
    if job["status"] != "AMBIGUOUS":
        raise ValueError("only AMBIGUOUS jobs can be reconciled")
    mark_done(conn, job_id, output_path, content_sha256)


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
    conn.execute(
        "UPDATE tts_queue_attempts SET status='FAILED', error_message=?, completed_at=? "
        "WHERE id=(SELECT id FROM tts_queue_attempts WHERE job_id=? AND status='STARTED' "
        "ORDER BY id DESC LIMIT 1)",
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
            "UPDATE tts_queue SET status='AMBIGUOUS', started_at=NULL, "
            "error_message=? WHERE id=? AND status='IN_PROGRESS'",
            (reason, row["id"]),
        )
        conn.execute(
            "INSERT INTO tts_queue_recoveries "
            "(job_id, recovered_at, previous_started_at, retry_count, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (row["id"], recovered_at, row["started_at"], row["retry_count"], reason),
        )
        conn.execute(
            "UPDATE tts_queue_attempts SET status='AMBIGUOUS', completed_at=?, error_message=? "
            "WHERE job_id=? AND status='STARTED'",
            (recovered_at, reason, row["id"]),
        )
    conn.commit()
    return [row["id"] for row in stale]
