"""Inspect and recover the durable TTS queue."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.tts_queue_db import get_job, init_tts_queue, recover_stale_jobs


def _connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_tts_queue(conn)
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="SQLite queue database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show queue counts")
    job_parser = subparsers.add_parser("job", help="Show one job")
    job_parser.add_argument("job_id", type=int)
    recover_parser = subparsers.add_parser("recover-stale", help="Requeue expired jobs")
    recover_parser.add_argument("--lease-timeout", type=float, required=True)

    args = parser.parse_args()
    conn = _connection(args.db)
    try:
        if args.command == "status":
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM tts_queue GROUP BY status"
            ).fetchall()
            counts = {status: 0 for status in ("PENDING", "IN_PROGRESS", "DONE", "FAILED")}
            counts.update({row["status"]: row["count"] for row in rows})
            print(json.dumps({"counts": counts}, sort_keys=True))
        elif args.command == "job":
            job = get_job(conn, args.job_id)
            if job is None:
                parser.error(f"No tts_queue job with id={args.job_id}")
            print(json.dumps(job, sort_keys=True, default=str))
        else:
            recovered = recover_stale_jobs(
                conn, lease_timeout_seconds=args.lease_timeout
            )
            print(json.dumps({"recovered": recovered}, sort_keys=True))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())