from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.utils.tts_queue_db import init_tts_queue


def _create_db(path: Path) -> int:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_tts_queue(conn)
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO tts_queue (text, voice_id, created_at) VALUES (?, ?, ?)",
        ("hello", "voice", now),
    )
    conn.commit()
    conn.close()
    return int(cursor.lastrowid)


def _run_cli(db_path: Path, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "tools/tts_queue.py", "--db", str(db_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_cli_reports_status_and_job_details(tmp_path: Path) -> None:
    row_id = _create_db(tmp_path / "queue.db")

    status = _run_cli(tmp_path / "queue.db", "status")
    job = _run_cli(tmp_path / "queue.db", "job", str(row_id))

    assert status["counts"]["PENDING"] == 1
    assert job["id"] == row_id
    assert job["status"] == "PENDING"


def test_cli_explicitly_recovers_stale_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "queue.db"
    row_id = _create_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE tts_queue SET status='IN_PROGRESS', started_at=? WHERE id=?",
        ("2020-01-01T00:00:00+00:00", row_id),
    )
    conn.commit()
    conn.close()

    result = _run_cli(db_path, "recover-stale", "--lease-timeout", "60")

    assert result["recovered"] == [row_id]