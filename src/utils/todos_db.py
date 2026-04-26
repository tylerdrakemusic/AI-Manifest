"""AI-Manifest todo card DB — binary done/not-done state.

Schema
------
todos(id, project, source, text, done, created_at, closed_at)

- project: key string matching PROJECTS in executive_audio_brief.py
  ('music', 'life', 'quantum', 'ai_manifest', 'workspace')
- source: 'AI' or 'TYLER'
- done: 0 = open, 1 = closed
- created_at / closed_at: ISO-8601 UTC strings
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "manifest_todos.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create todos table and unique index if they don't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project    TEXT NOT NULL,
                source     TEXT NOT NULL CHECK(source IN ('AI', 'TYLER')),
                text       TEXT NOT NULL,
                done       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at  TEXT
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_todos_project_source_text
            ON todos(project, source, text)
        """)
        conn.commit()


def count_todos() -> int:
    """Return total number of rows in the todos table (open + done)."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM todos").fetchone()
    return row[0] if row else 0


def get_open_todos(project: str | None = None) -> list[dict[str, Any]]:
    """Return all open (done=0) todos, optionally filtered by project."""
    with get_connection() as conn:
        if project:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=0 AND project=? ORDER BY id",
                (project,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=0 ORDER BY project, source, id"
            ).fetchall()
    return [dict(r) for r in rows]


def get_done_todos(project: str | None = None) -> list[dict[str, Any]]:
    """Return all done (done=1) todos, optionally filtered by project."""
    with get_connection() as conn:
        if project:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=1 AND project=? ORDER BY closed_at DESC",
                (project,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=1 ORDER BY closed_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def mark_done(todo_id: int) -> bool:
    """Flip done=1 and set closed_at for a single todo. Returns True on success."""
    closed_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET done=1, closed_at=? WHERE id=? AND done=0",
            (closed_at, todo_id),
        )
        conn.commit()
    return cur.rowcount == 1


def insert_todo(project: str, source: str, text: str) -> int | None:
    """Insert a todo; returns new row id or None if it already exists (idempotent)."""
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO todos (project, source, text, done, created_at)"
                " VALUES (?, ?, ?, 0, ?)",
                (project, source, text, created_at),
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # duplicate — skip silently
