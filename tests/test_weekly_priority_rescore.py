"""Tests for tools/weekly_priority_rescore.py.

All tests use in-memory SQLite — the real manifest_todos.db is never touched.
"""
from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so src.* imports resolve
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

_CREATE_TODOS = """
CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project      TEXT NOT NULL,
    source       TEXT NOT NULL,
    text         TEXT NOT NULL,
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    closed_at    TEXT,
    priority     INTEGER NOT NULL DEFAULT 5,
    autonomy_level TEXT NOT NULL DEFAULT 'supervised'
)
"""

_CREATE_PRIORITY_HISTORY = """
CREATE TABLE IF NOT EXISTS priority_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    todo_id    INTEGER NOT NULL REFERENCES todos(id),
    priority   INTEGER NOT NULL,
    scored_at  TEXT NOT NULL
)
"""


def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TODOS)
    conn.execute(_CREATE_PRIORITY_HISTORY)
    conn.commit()
    return conn


def _insert_todo(conn: sqlite3.Connection, project: str, text: str, priority: int, done: int = 0) -> int:
    cur = conn.execute(
        "INSERT INTO todos (project, source, text, done, created_at, priority) VALUES (?,?,?,?,?,?)",
        (project, "AI", text, done, datetime.now(timezone.utc).isoformat(), priority),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_history(conn: sqlite3.Connection, todo_id: int, priority: int, scored_at: str) -> None:
    conn.execute(
        "INSERT INTO priority_history (todo_id, priority, scored_at) VALUES (?,?,?)",
        (todo_id, priority, scored_at),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Patch helpers — redirect todos_db to in-memory DB
# ---------------------------------------------------------------------------

def _patch_db(mem_conn: sqlite3.Connection, monkeypatch, tmp_path: Path):
    """Redirect todos_db module to use an in-memory connection and a temp JSONL log."""
    import tools.weekly_priority_rescore as rescore_mod
    import src.utils.todos_db as todos_db_mod

    # Patch get_connection to return the mem_conn (as a context-manager-safe wrapper)
    class _CtxConn:
        def __enter__(self):
            return mem_conn
        def __exit__(self, *_):
            pass

    monkeypatch.setattr(rescore_mod, "get_connection", lambda: _CtxConn())
    monkeypatch.setattr(todos_db_mod, "get_connection", lambda: _CtxConn())

    # Patch get_open_todos to query the in-memory DB
    def _get_open_todos(project=None):
        rows = mem_conn.execute("SELECT * FROM todos WHERE done=0").fetchall()
        return [dict(r) for r in rows]
    monkeypatch.setattr(rescore_mod, "get_open_todos", _get_open_todos)

    # Patch update_priority to use in-memory DB
    def _update_priority(todo_id: int, priority: int) -> bool:
        from datetime import datetime, timezone
        scored_at = datetime.now(timezone.utc).isoformat()
        cur = mem_conn.execute("UPDATE todos SET priority=? WHERE id=?", (priority, todo_id))
        if cur.rowcount == 1:
            mem_conn.execute(
                "INSERT INTO priority_history (todo_id, priority, scored_at) VALUES (?,?,?)",
                (todo_id, priority, scored_at),
            )
        mem_conn.commit()
        return cur.rowcount == 1
    monkeypatch.setattr(rescore_mod, "update_priority", _update_priority)

    # Patch init_db to no-op (already initialised)
    monkeypatch.setattr(rescore_mod, "init_db", lambda: None)

    # Redirect JSONL log to tmp_path
    jsonl_path = tmp_path / "priority_rescore.jsonl"
    monkeypatch.setattr(rescore_mod, "JSONL_LOG", jsonl_path)

    return jsonl_path


# ===========================================================================
# Tests
# ===========================================================================

class TestRescoreChangesApplied:
    """All open todos are scored; non-stale changes are written to DB."""

    def test_priority_updated_in_db(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        tid = _insert_todo(mem_conn, "music", "Mix the new track", priority=3)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)

        # score_priority always returns 7 for this test
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 7)

        exit_code = rescore_mod.run(dry_run=False)

        assert exit_code == 0
        row = mem_conn.execute("SELECT priority FROM todos WHERE id=?", (tid,)).fetchone()
        assert row["priority"] == 7

    def test_jsonl_line_written(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        _insert_todo(mem_conn, "music", "Master the EP", priority=3)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 8)

        rescore_mod.run(dry_run=False)

        assert jsonl_path.exists()
        line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
        assert line["old_priority"] == 3
        assert line["new_priority"] == 8
        assert "run_id" in line
        assert "ts" in line

    def test_no_change_no_jsonl_entry(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        _insert_todo(mem_conn, "music", "Already optimal", priority=5)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)
        # score returns same as current priority — no change
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 5)

        rescore_mod.run(dry_run=False)

        assert not jsonl_path.exists()


class TestStaleDetection:
    """Stale item is detected (stale=True in JSONL) when no recent history."""

    def test_stale_item_flagged(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        tid = _insert_todo(mem_conn, "life", "Critical health check", priority=8)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)
        # Returns a lower priority so a change is written
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 5)

        rescore_mod.run(dry_run=False)

        line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
        assert line["todo_id"] == tid
        assert line["stale"] is True


class TestNonStaleHighPriority:
    """High-priority item with a RECENT history entry must NOT be flagged stale."""

    def test_recent_history_not_stale(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        tid = _insert_todo(mem_conn, "quantum", "Run qubit calibration", priority=9)
        # Insert a recent history row (1 day ago — well within STALE_DAYS=30)
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        _insert_history(mem_conn, tid, 9, recent)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)
        # Return a different priority so a change IS written (to inspect stale flag)
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 6)

        rescore_mod.run(dry_run=False)

        line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
        assert line["todo_id"] == tid
        assert line["stale"] is False


class TestDryRun:
    """--dry-run must not write to DB or JSONL."""

    def test_dry_run_skips_db_write(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        tid = _insert_todo(mem_conn, "workspace", "Refactor portal", priority=3)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 9)

        rescore_mod.run(dry_run=True)

        # DB priority unchanged
        row = mem_conn.execute("SELECT priority FROM todos WHERE id=?", (tid,)).fetchone()
        assert row["priority"] == 3

    def test_dry_run_skips_jsonl_write(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        _insert_todo(mem_conn, "workspace", "Add feature X", priority=2)

        import tools.weekly_priority_rescore as rescore_mod
        jsonl_path = _patch_db(mem_conn, monkeypatch, tmp_path)
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 9)

        rescore_mod.run(dry_run=True)

        assert not jsonl_path.exists()


class TestPriorityHistoryInsertion:
    """A priority_history row is inserted after a priority update."""

    def test_history_row_inserted(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        tid = _insert_todo(mem_conn, "ai_manifest", "Deploy voice model", priority=4)

        import tools.weekly_priority_rescore as rescore_mod
        _patch_db(mem_conn, monkeypatch, tmp_path)
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 8)

        rescore_mod.run(dry_run=False)

        rows = mem_conn.execute(
            "SELECT * FROM priority_history WHERE todo_id=?", (tid,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["priority"] == 8

    def test_no_history_row_on_no_change(self, monkeypatch, tmp_path):
        mem_conn = _make_mem_conn()
        tid = _insert_todo(mem_conn, "ai_manifest", "Keep same priority", priority=6)

        import tools.weekly_priority_rescore as rescore_mod
        _patch_db(mem_conn, monkeypatch, tmp_path)
        # Same priority — update_priority never called
        monkeypatch.setattr(rescore_mod, "score_priority", lambda text, project: 6)

        rescore_mod.run(dry_run=False)

        rows = mem_conn.execute(
            "SELECT * FROM priority_history WHERE todo_id=?", (tid,)
        ).fetchall()
        assert len(rows) == 0
