"""Weekly priority re-scorer for manifest_todos.db.

Loads all open todos, re-scores each via score_priority(), detects stale
high-priority items (no recent priority_history entry), auto-downgrades them,
and appends a JSONL diff log.

Usage
-----
    C:\\G\\python.exe tools/weekly_priority_rescore.py [--dry-run]

Constants
---------
STALE_HIGH_PRI_THRESHOLD : items at or above this priority are considered "high"
STALE_DAYS               : days without a priority_history entry = stale
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add the project root to sys.path so src.* imports work when invoked directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.priority_scorer import score_priority
from src.utils.todos_db import get_connection, get_open_todos, init_db, update_priority

STALE_HIGH_PRI_THRESHOLD: int = 7
STALE_DAYS: int = 30

JSONL_LOG = _PROJECT_ROOT / "logs" / "priority_rescore.jsonl"


def _get_latest_history_date(conn, todo_id: int) -> datetime | None:
    """Return the UTC datetime of the most recent priority_history row for todo_id, or None."""
    row = conn.execute(
        "SELECT scored_at FROM priority_history WHERE todo_id=? ORDER BY id DESC LIMIT 1",
        (todo_id,),
    ).fetchone()
    if not row:
        return None
    try:
        return datetime.fromisoformat(str(row[0]))
    except (ValueError, TypeError):
        return None


def _is_stale(conn, todo: dict, now: datetime) -> bool:
    """Return True if the todo is high-priority and has no recent history entry."""
    if todo.get("priority", 0) < STALE_HIGH_PRI_THRESHOLD:
        return False
    cutoff = now - timedelta(days=STALE_DAYS)
    last_scored = _get_latest_history_date(conn, todo["id"])
    if last_scored is None:
        return True
    # Normalise to offset-aware for comparison
    if last_scored.tzinfo is None:
        last_scored = last_scored.replace(tzinfo=timezone.utc)
    return last_scored < cutoff


def run(dry_run: bool = False) -> int:
    """Execute the weekly rescore. Returns exit code (0 = success)."""
    init_db()

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    todos = get_open_todos()

    scanned = 0
    changed = 0
    stale_detected = 0
    failed = 0
    log_lines: list[dict] = []

    with get_connection() as conn:
        for todo in todos:
            scanned += 1
            todo_id: int = todo["id"]
            old_priority: int = todo.get("priority", 5)
            project: str = todo.get("project", "")

            try:
                new_priority = score_priority(todo["text"], project)
            except Exception:
                failed += 1
                continue

            stale = _is_stale(conn, todo, now)
            if stale:
                stale_detected += 1

            if new_priority == old_priority:
                continue

            changed += 1
            entry = {
                "run_id": run_id,
                "ts": now.isoformat(),
                "todo_id": todo_id,
                "project": project,
                "old_priority": old_priority,
                "new_priority": new_priority,
                "stale": stale,
            }
            log_lines.append(entry)

            if not dry_run:
                update_priority(todo_id, new_priority)

    if not dry_run and log_lines:
        JSONL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with JSONL_LOG.open("a", encoding="utf-8") as fh:
            for entry in log_lines:
                fh.write(json.dumps(entry) + "\n")

    print(
        f"[priority-rescore] run_id={run_id} dry_run={dry_run} "
        f"scanned={scanned} changed={changed} stale_detected={stale_detected} failed={failed}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly todo priority re-scorer")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Score but do not write to DB or JSONL log",
    )
    args = parser.parse_args()

    try:
        exit_code = run(dry_run=args.dry_run)
    except Exception:
        traceback.print_exc()
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
