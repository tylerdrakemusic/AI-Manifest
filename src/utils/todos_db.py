"""AI-Manifest todo card DB — binary done/not-done state.

Schema
------
todos(id, project, source, text, done, created_at, closed_at, perfected_at)

- project: canonical lowercase key ('music', 'life', 'capital', 'quantum', 'ai_manifest',
  'workspace'). Sigil display names (e.g. '❤Music', '∞Life') are automatically
  normalised to the canonical key by _normalize_project() at read/write time.
- source: 'AI', 'TYLER', or 'SCAN'
- done: 0 = open, 1 = closed
- created_at / closed_at: ISO-8601 UTC strings
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "manifest_todos.db"
ALLOWED_SOURCES = ("AI", "TYLER", "SCAN")
ALLOWED_AUTONOMY_LEVELS = ("full", "supervised", "human")
FR_ID_PATTERN = re.compile(r"^FR-\d{8}-[a-z0-9][a-z0-9-]*$")


def resolve_worktree_db_path(start: Path, max_levels: int = 5) -> Path | None:
    """Walk up from `start` looking for src/data/manifest_todos.db.

    Git worktrees under `<main>/.worktrees/<branch>/` have their own empty
    `data/` dir, so the default DB_PATH resolution above finds no DB there.
    This walks up parent directories to find the main project root's live DB.
    Returns None if not found within `max_levels` levels (e.g. when actually
    running from the main tree, where the default DB_PATH is already correct).
    """
    candidate = start
    for _ in range(max_levels):
        db = candidate / "src" / "data" / "manifest_todos.db"
        if db.exists():
            return db
        candidate = candidate.parent
    return None


def use_worktree_aware_db_path(start: Path) -> None:
    """Switch module-level DB_PATH to the main project's live DB if `start`
    is inside a git worktree that lacks its own data.

    Call once, near the top of any `tools/*.py` script that touches
    manifest_todos.db directly, before importing from this module:

        _ROOT = Path(__file__).resolve().parent.parent
        import utils.todos_db as todos_db
        todos_db.use_worktree_aware_db_path(_ROOT)
    """
    global DB_PATH
    resolved = resolve_worktree_db_path(start)
    if resolved is not None:
        DB_PATH = resolved

# Map sigil/display project names → canonical DB keys.
# Agents writing directly via SQL sometimes use the display name; normalise at
# write time so the executive dashboard (which queries by lowercase key) always
# finds the rows.
_SIGIL_TO_KEY: dict[str, str] = {
    "∞Life":        "life",
    "❤Music":       "music",
    "⟨ψ⟩Quantum":   "quantum",
    "👁AI-Manifest": "ai_manifest",
    "ΣCapital":      "capital",
    "⊕Workspace":   "workspace",
}


def _normalize_project(project: str) -> str:
    """Return the canonical lowercase DB key for a project name."""
    return _SIGIL_TO_KEY.get(project, project)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # nosec B608 — PRAGMA does not support parameterized queries; table name is always a hardcoded literal from internal callers
    return any(r[1] == column for r in rows)


def _table_allows_scan_source(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='todos'"
    ).fetchone()
    if not row or not row[0]:
        return False
    sql = str(row[0])
    return "'SCAN'" in sql


def _migrate_todos_for_scan_source(conn: sqlite3.Connection) -> None:
    # Rebuild the table because SQLite cannot ALTER an existing CHECK constraint.
    conn.execute("BEGIN")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS todos_new (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project    TEXT NOT NULL,
                source     TEXT NOT NULL CHECK(source IN ('AI', 'TYLER', 'SCAN')),
                text       TEXT NOT NULL,
                done       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at  TEXT,
                priority   INTEGER NOT NULL DEFAULT 5,
                fr_id      TEXT,
                perfected_at TEXT
            )
        """)
        conn.execute("""
            INSERT INTO todos_new (id, project, source, text, done, created_at, closed_at, priority, fr_id, perfected_at)
            SELECT id, project, source, text, done, created_at, closed_at, priority, fr_id, perfected_at
            FROM todos
        """)
        conn.execute("DROP TABLE todos")
        conn.execute("ALTER TABLE todos_new RENAME TO todos")
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_todos_project_source_text
            ON todos(project, source, text)
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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
                source     TEXT NOT NULL CHECK(source IN ('AI', 'TYLER', 'SCAN')),
                text       TEXT NOT NULL,
                done       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at  TEXT,
                priority   INTEGER NOT NULL DEFAULT 5,
                fr_id      TEXT,
                perfected_at TEXT
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_todos_project_source_text
            ON todos(project, source, text)
        """)
        # Migration guard: add priority column to existing DBs
        try:
            conn.execute(
                "ALTER TABLE todos ADD COLUMN priority INTEGER NOT NULL DEFAULT 5"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

        # Migration guards needed before a possible table rebuild so the
        # rebuild can preserve these fields from older schemas.
        for _column in ("fr_id", "perfected_at"):
            try:
                conn.execute(f"ALTER TABLE todos ADD COLUMN {_column} TEXT")  # nosec B608 — column names are hardcoded above
            except sqlite3.OperationalError:
                pass  # column already exists

        if _has_column(conn, "todos", "priority") and not _table_allows_scan_source(conn):
            _migrate_todos_for_scan_source(conn)

        # Migration guard: add autonomy_level column to existing DBs
        try:
            conn.execute(
                "ALTER TABLE todos ADD COLUMN autonomy_level TEXT NOT NULL DEFAULT 'supervised'"
                " CHECK(autonomy_level IN ('full', 'supervised', 'human'))"
            )
        except sqlite3.OperationalError:
            pass  # column already exists

        # Backfill any rows that slipped through with NULL or empty string
        conn.execute(
            "UPDATE todos SET autonomy_level = 'supervised'"
            " WHERE autonomy_level IS NULL OR autonomy_level = ''"
        )

        # Migration guard: add priority_history table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS priority_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                todo_id    INTEGER NOT NULL REFERENCES todos(id),
                priority   INTEGER NOT NULL,
                scored_at  TEXT NOT NULL
            )
        """)

        # Migration guard: add rich-context columns (AC-2)
        for _col, _default in [
            ("rationale", None),
            ("implementation_hints", None),
            ("context_snapshot", None),
            ("estimated_effort", None),
            ("dependencies", None),
        ]:
            if not _has_column(conn, "todos", _col):
                conn.execute(f"ALTER TABLE todos ADD COLUMN {_col} TEXT")  # nosec B608 — col name is a hardcoded literal

        conn.commit()


def count_todos() -> int:
    """Return total number of rows in the todos table (open + done)."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM todos").fetchone()
    return row[0] if row else 0


def get_open_todos(project: str | None = None) -> list[dict[str, Any]]:
    """Return all open (done=0) todos, optionally filtered by project."""
    if project:
        project = _normalize_project(project)
    with get_connection() as conn:
        if project:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=0 AND project=? ORDER BY priority DESC, id ASC",
                (project,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=0 ORDER BY project, source, priority DESC, id ASC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_done_todos(project: str | None = None) -> list[dict[str, Any]]:
    """Return all done (done=1) todos, optionally filtered by project."""
    if project:
        project = _normalize_project(project)
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


def add_todo(
    project: str,
    text: str,
    priority: int = 5,
    source: str = "TYLER",
    autonomy_level: str = "supervised",
    rationale: str | None = None,
    implementation_hints: str | None = None,
    context_snapshot: str | None = None,
    estimated_effort: str | None = None,
    dependencies: str | None = None,
) -> int:
    """Insert a new todo and return its id. Raises ValueError for invalid priority."""
    project = _normalize_project(project)
    if priority not in range(1, 11):
        raise ValueError(f"priority must be 1-10, got {priority!r}")
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of {ALLOWED_SOURCES!r}, got {source!r}")
    if autonomy_level not in ALLOWED_AUTONOMY_LEVELS:
        raise ValueError(f"autonomy_level must be one of {ALLOWED_AUTONOMY_LEVELS!r}, got {autonomy_level!r}")
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO todos"
            " (project, source, text, done, created_at, priority, autonomy_level,"
            "  rationale, implementation_hints, context_snapshot, estimated_effort, dependencies)"
            " VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project, source, text, created_at, priority, autonomy_level,
                rationale, implementation_hints, context_snapshot,
                estimated_effort, dependencies,
            ),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def update_priority(todo_id: int, priority: int) -> bool:
    """Update priority for a single todo and record the change in priority_history. Returns True on success."""
    if priority not in range(1, 11):
        raise ValueError(f"priority must be 1-10, got {priority!r}")
    scored_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET priority=? WHERE id=?",
            (priority, todo_id),
        )
        if cur.rowcount == 1:
            conn.execute(
                "INSERT INTO priority_history (todo_id, priority, scored_at) VALUES (?, ?, ?)",
                (todo_id, priority, scored_at),
            )
        conn.commit()
    return cur.rowcount == 1


def get_todo_by_id(todo_id: int) -> dict[str, Any] | None:
    """Return a single todo row by id, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM todos WHERE id=?", (todo_id,)
        ).fetchone()
    return dict(row) if row else None


def link_todo_to_fr(todo_id: int, fr_id: str) -> bool:
    """Link one unlinked todo to a syntactically valid feature request."""
    if not FR_ID_PATTERN.fullmatch(fr_id):
        raise ValueError(f"invalid FR id: {fr_id!r}")
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET fr_id=? WHERE id=? AND fr_id IS NULL",
            (fr_id, todo_id),
        )
        conn.commit()
    return cur.rowcount == 1


def insert_todo(
    project: str,
    source: str,
    text: str,
    autonomy_level: str = "supervised",
) -> int | None:
    """Insert a todo; returns new row id or None if it already exists (idempotent)."""
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of {ALLOWED_SOURCES!r}, got {source!r}")
    if autonomy_level not in ALLOWED_AUTONOMY_LEVELS:
        raise ValueError(f"autonomy_level must be one of {ALLOWED_AUTONOMY_LEVELS!r}, got {autonomy_level!r}")
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO todos (project, source, text, done, created_at, autonomy_level)"
                " VALUES (?, ?, ?, 0, ?, ?)",
                (project, source, text, created_at, autonomy_level),
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # duplicate — skip silently


def get_open_todos_by_autonomy(
    autonomy_level: str,
    project: str | None = None,
) -> list[dict[str, Any]]:
    """Return open todos filtered by autonomy_level, sorted by priority DESC."""
    if autonomy_level not in ALLOWED_AUTONOMY_LEVELS:
        raise ValueError(f"autonomy_level must be one of {ALLOWED_AUTONOMY_LEVELS!r}, got {autonomy_level!r}")
    with get_connection() as conn:
        if project:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=0 AND autonomy_level=? AND project=?"
                " ORDER BY priority DESC, id ASC",
                (autonomy_level, project),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM todos WHERE done=0 AND autonomy_level=?"
                " ORDER BY priority DESC, id ASC",
                (autonomy_level,),
            ).fetchall()
    return [dict(r) for r in rows]
