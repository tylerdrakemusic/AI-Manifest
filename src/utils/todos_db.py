"""AI-Manifest todo card DB — binary done/not-done state.

Schema
------
todos(id, project, source, text, done, created_at, closed_at, closure_reason, perfected_at)

- project: canonical lowercase key ('music', 'life', 'capital', 'quantum', 'ai_manifest',
  'workspace'). Sigil display names (e.g. '❤Music', '∞Life') are automatically
  normalised to the canonical key by _normalize_project() at read/write time.
- source: 'AI', 'TYLER', or 'SCAN'
- done: 0 = open, 1 = closed
- created_at / closed_at: ISO-8601 UTC strings
- closure_reason: completed, cancelled, stale, or NULL for legacy open rows
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "manifest_todos.db"
ALLOWED_SOURCES = ("AI", "TYLER", "SCAN")
ALLOWED_AUTONOMY_LEVELS = ("full", "supervised", "human")
ALLOWED_DECISIONS = ("proceed", "defer", "reject")
ALLOWED_BENEFIT_CATEGORIES = (
    "user", "system", "strategic", "revenue", "risk_reduction", "learning",
    "maintenance", "compliance",
)
ALLOWED_IMPACTS = ("low", "medium", "high")
FR_ID_PATTERN = re.compile(r"^FR-\d{8}-[a-z0-9][a-z0-9-]*$")
TERMINAL_STATES = frozenset({"completed", "cancelled", "stale"})
DEFAULT_TERMINAL_STATES = TERMINAL_STATES


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
    closed_at_expression = "closed_at" if _has_column(conn, "todos", "closed_at") else "NULL"
    closure_reason_expression = "closure_reason" if _has_column(conn, "todos", "closure_reason") else "NULL"
    parent_expression = "parent_id" if _has_column(conn, "todos", "parent_id") else "NULL"
    dependencies_expression = "dependencies" if _has_column(conn, "todos", "dependencies") else "NULL"
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
                closure_reason TEXT CHECK(closure_reason IN ('completed', 'cancelled', 'stale')),
                priority   INTEGER NOT NULL DEFAULT 5,
                fr_id      TEXT,
                perfected_at TEXT,
                parent_id INTEGER,
                dependencies TEXT
            )
        """)
        conn.execute("""
            INSERT INTO todos_new (id, project, source, text, done, created_at, closed_at, closure_reason, priority, fr_id, perfected_at, parent_id, dependencies)
            SELECT id, project, source, text, done, created_at, {closed_at_expression}, {closure_reason_expression}, priority, fr_id, perfected_at, {parent_expression}, {dependencies_expression}
            FROM todos
        """.format(
            closed_at_expression=closed_at_expression,
            closure_reason_expression=closure_reason_expression,
            parent_expression=parent_expression,
            dependencies_expression=dependencies_expression,
        ))
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


def _create_graph_schema(conn: sqlite3.Connection) -> None:
    """Create normalized prerequisite and FR-link tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS todo_prerequisites (
            todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
            prerequisite_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
            allowed_terminal_states TEXT NOT NULL DEFAULT '["completed", "cancelled", "stale"]',
            created_at TEXT NOT NULL,
            PRIMARY KEY (todo_id, prerequisite_id),
            CHECK(todo_id <> prerequisite_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS todo_fr_links (
            todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
            fr_id TEXT NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0, 1)),
            created_at TEXT NOT NULL,
            PRIMARY KEY (todo_id, fr_id)
        )
    """)


def _ensure_decision_metadata_schema(conn: sqlite3.Connection) -> None:
    """Create the canonical assessment tables while preserving legacy tables."""
    current_columns = {
        "todo_id", "expected_value", "user_or_system_benefit", "strategic_alignment",
        "confidence", "cost_of_delay", "primary_benefit_category",
        "secondary_benefit_category", "benefit_summary", "justification", "evidence",
        "assessed_by", "updated_at",
    }
    history_columns = current_columns - {"updated_at"} | {"assessed_at", "id"}
    for table, required_columns, suffix in (
        ("todo_decision_metadata", current_columns, "legacy"),
        ("todo_decision_assessments", history_columns, "legacy"),
    ):
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if existing and not required_columns.issubset(existing):
            legacy_table = f"{table}_{suffix}"
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (legacy_table,)
            ).fetchone():
                conn.execute(f"ALTER TABLE {table} RENAME TO {legacy_table}")  # nosec B608 — table names are internal constants

    conn.execute("""
        CREATE TABLE IF NOT EXISTS todo_decision_metadata (
            todo_id INTEGER PRIMARY KEY REFERENCES todos(id) ON DELETE CASCADE,
            expected_value TEXT NOT NULL,
            user_or_system_benefit TEXT NOT NULL,
            strategic_alignment TEXT NOT NULL,
            confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 10),
            cost_of_delay TEXT NOT NULL,
            primary_benefit_category TEXT NOT NULL,
            secondary_benefit_category TEXT,
            benefit_summary TEXT NOT NULL,
            justification TEXT NOT NULL,
            evidence TEXT NOT NULL,
            assessed_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS todo_decision_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
            expected_value TEXT NOT NULL,
            user_or_system_benefit TEXT NOT NULL,
            strategic_alignment TEXT NOT NULL,
            confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 10),
            cost_of_delay TEXT NOT NULL,
            primary_benefit_category TEXT NOT NULL,
            secondary_benefit_category TEXT,
            benefit_summary TEXT NOT NULL,
            justification TEXT NOT NULL,
            evidence TEXT NOT NULL,
            assessed_by TEXT NOT NULL,
            assessed_at TEXT NOT NULL
        )
    """)


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
                closure_reason TEXT CHECK(closure_reason IN ('completed', 'cancelled', 'stale')),
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

        try:
            conn.execute(
                "ALTER TABLE todos ADD COLUMN closure_reason TEXT"
                " CHECK(closure_reason IN ('completed', 'cancelled', 'stale'))"
            )
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

        if not _has_column(conn, "todos", "parent_id"):
            conn.execute("ALTER TABLE todos ADD COLUMN parent_id INTEGER")

        _create_graph_schema(conn)

        _ensure_decision_metadata_schema(conn)

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


def mark_done(todo_id: int, *, force: bool = False) -> bool:
    """Complete one open todo, optionally bypassing prerequisite readiness."""
    closed_at = datetime.now(timezone.utc).isoformat()
    if not force and not can_complete_todo(todo_id)["ready"]:
        return False
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET done=1, closed_at=?, closure_reason='completed'"
            " WHERE id=? AND done=0",
            (closed_at, todo_id),
        )
        conn.commit()
    return cur.rowcount == 1


def cancel_todo(todo_id: int) -> bool:
    """Close one open todo as cancelled and return whether it was updated."""
    closed_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET done=1, closed_at=?, closure_reason='cancelled'"
            " WHERE id=? AND done=0",
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
    parent_id: int | None = None,
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
            "  rationale, implementation_hints, context_snapshot, estimated_effort, dependencies, parent_id)"
            " VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project, source, text, created_at, priority, autonomy_level,
                rationale, implementation_hints, context_snapshot,
                estimated_effort, dependencies, parent_id,
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


def _validate_decision_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    required = {
        "expected_value", "user_or_system_benefit", "strategic_alignment", "confidence",
        "cost_of_delay", "primary_benefit_category", "benefit_summary", "justification",
        "evidence",
    }
    missing = required.difference(metadata)
    if missing:
        raise ValueError(f"decision metadata is missing required fields: {sorted(missing)!r}")
    allowed = required | {"secondary_benefit_category"}
    unexpected = set(metadata).difference(allowed)
    if unexpected:
        raise ValueError(f"decision metadata has unexpected fields: {sorted(unexpected)!r}")
    if metadata["primary_benefit_category"] not in ALLOWED_BENEFIT_CATEGORIES:
        raise ValueError(f"primary_benefit_category must be one of {ALLOWED_BENEFIT_CATEGORIES!r}")
    secondary = metadata.get("secondary_benefit_category")
    if secondary is not None and secondary not in ALLOWED_BENEFIT_CATEGORIES:
        raise ValueError(f"secondary_benefit_category must be one of {ALLOWED_BENEFIT_CATEGORIES!r}")
    if not isinstance(metadata["confidence"], int) or isinstance(metadata["confidence"], bool) or metadata["confidence"] not in range(1, 11):
        raise ValueError("confidence must be an integer from 1-10")
    for field in required - {"confidence", "evidence"}:
        if not isinstance(metadata[field], str) or not metadata[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if not isinstance(metadata["evidence"], list) or not all(isinstance(item, str) and item.strip() for item in metadata["evidence"]):
        raise ValueError("evidence must be a non-empty list of strings")
    return metadata


def set_decision_metadata(todo_id: int, metadata: dict[str, Any], *, assessed_by: str) -> None:
    """Validate and transactionally replace current metadata and append an assessment."""
    metadata = _validate_decision_metadata(metadata)
    if not isinstance(assessed_by, str) or not assessed_by.strip():
        raise ValueError("assessed_by must be a non-empty string")
    now = datetime.now(timezone.utc).isoformat()
    evidence = json.dumps(metadata["evidence"], ensure_ascii=False)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            todo = conn.execute("SELECT priority, estimated_effort FROM todos WHERE id=?", (todo_id,)).fetchone()
            if todo is None:
                raise ValueError("todo not found")
            effort = str(todo["estimated_effort"] or "").strip().lower()
            oversized = effort in {"large", "xl", "x-large", "oversized"}
            if (int(todo["priority"]) >= 8 or oversized) and not metadata["evidence"]:
                raise ValueError("high-impact or oversized decision metadata requires evidence")
            values = tuple(metadata[field] for field in (
                "expected_value", "user_or_system_benefit", "strategic_alignment", "confidence",
                "cost_of_delay", "primary_benefit_category",
            )) + (
                metadata.get("secondary_benefit_category"), metadata["benefit_summary"],
                metadata["justification"], evidence, assessed_by, now,
            )
            conn.execute("""
                INSERT INTO todo_decision_metadata
                    (todo_id, expected_value, user_or_system_benefit, strategic_alignment,
                     confidence, cost_of_delay, primary_benefit_category,
                     secondary_benefit_category, benefit_summary, justification,
                     evidence, assessed_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(todo_id) DO UPDATE SET
                    expected_value=excluded.expected_value, user_or_system_benefit=excluded.user_or_system_benefit,
                    strategic_alignment=excluded.strategic_alignment, confidence=excluded.confidence,
                    cost_of_delay=excluded.cost_of_delay, primary_benefit_category=excluded.primary_benefit_category,
                    secondary_benefit_category=excluded.secondary_benefit_category, benefit_summary=excluded.benefit_summary,
                    justification=excluded.justification, evidence=excluded.evidence, assessed_by=excluded.assessed_by,
                    updated_at=excluded.updated_at
            """, (todo_id, *values))
            conn.execute("""
                INSERT INTO todo_decision_assessments
                    (todo_id, expected_value, user_or_system_benefit, strategic_alignment,
                     confidence, cost_of_delay, primary_benefit_category,
                     secondary_benefit_category, benefit_summary, justification,
                     evidence, assessed_by, assessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (todo_id, *values))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _decision_metadata(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result.pop("id", None)
    result.pop("todo_id", None)
    result.pop("updated_at", None)
    result.pop("assessed_at", None)
    result.pop("assessed_by", None)
    result["evidence"] = json.loads(result["evidence"])
    if result.get("secondary_benefit_category") is None:
        result.pop("secondary_benefit_category", None)
    return result


def get_decision_metadata(todo_id: int) -> dict[str, Any] | None:
    """Return normalized current decision metadata without legacy fabrication."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM todo_decision_metadata WHERE todo_id=?", (todo_id,)).fetchone()
    return _decision_metadata(row) if row else None


def get_decision_assessments(todo_id: int) -> list[dict[str, Any]]:
    """Return append-only decision assessments from oldest to newest."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM todo_decision_assessments WHERE todo_id=? ORDER BY id",
            (todo_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "metadata": _decision_metadata(row),
            "assessed_by": row["assessed_by"],
            "assessed_at": row["assessed_at"],
        }
        for row in rows
    ]


def get_priority_guidance(todo_id: int) -> dict[str, Any]:
    """Return advisory priority guidance without changing the todo priority."""
    todo = get_todo_by_id(todo_id)
    if todo is None:
        raise ValueError("todo not found")
    metadata = get_decision_metadata(todo_id)
    return {
        "todo_id": todo_id,
        "current_priority": todo["priority"],
        "recommended_priority": metadata["confidence"] if metadata else None,
        "advisory": True,
    }


def get_todo_by_id(todo_id: int) -> dict[str, Any] | None:
    """Return a single todo row by id, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM todos WHERE id=?", (todo_id,)
        ).fetchone()
    return dict(row) if row else None


def _terminal_policy(states: Iterable[str] | None) -> list[str]:
    policy = DEFAULT_TERMINAL_STATES if states is None else frozenset(states)
    if not policy or not policy.issubset(TERMINAL_STATES):
        raise ValueError(f"allowed terminal states must be a non-empty subset of {sorted(TERMINAL_STATES)!r}")
    return sorted(policy)


def link_prerequisite(
    todo_id: int,
    prerequisite_id: int,
    allowed_terminal_states: Iterable[str] | None = None,
) -> bool:
    """Atomically add a prerequisite edge, rejecting cycles."""
    policy = _terminal_policy(allowed_terminal_states)
    if todo_id == prerequisite_id:
        raise ValueError("prerequisite cycle rejected")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            exists = conn.execute(
                "SELECT COUNT(*) FROM todos WHERE id IN (?, ?)",
                (todo_id, prerequisite_id),
            ).fetchone()[0]
            if exists != 2:
                raise ValueError("todo and prerequisite must exist")
            reaches_dependent = conn.execute(
                """
                WITH RECURSIVE reachable(id) AS (
                    SELECT prerequisite_id FROM todo_prerequisites WHERE todo_id=?
                    UNION
                    SELECT edge.prerequisite_id
                    FROM todo_prerequisites edge JOIN reachable ON edge.todo_id=reachable.id
                )
                SELECT 1 FROM reachable WHERE id=?
                """,
                (prerequisite_id, todo_id),
            ).fetchone()
            if reaches_dependent:
                raise ValueError("prerequisite cycle rejected")
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO todo_prerequisites
                    (todo_id, prerequisite_id, allowed_terminal_states, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (todo_id, prerequisite_id, json.dumps(policy), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return cur.rowcount == 1
        except Exception:
            conn.rollback()
            raise


def _graph_rows(sql: str, todo_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(sql, (todo_id,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["allowed_terminal_states"] = json.loads(item.pop("_policy"))
        result.append(item)
    return result


def get_required_todos(todo_id: int) -> list[dict[str, Any]]:
    """Return direct prerequisites for a todo, including edge policies."""
    return _graph_rows(
        """
        SELECT prerequisite.*, edge.allowed_terminal_states AS _policy
        FROM todo_prerequisites edge JOIN todos prerequisite ON prerequisite.id=edge.prerequisite_id
        WHERE edge.todo_id=? ORDER BY prerequisite.id
        """,
        todo_id,
    )


def get_required_by_todos(todo_id: int) -> list[dict[str, Any]]:
    """Return direct todos that require the supplied todo."""
    return _graph_rows(
        """
        SELECT dependent.*, edge.allowed_terminal_states AS _policy
        FROM todo_prerequisites edge JOIN todos dependent ON dependent.id=edge.todo_id
        WHERE edge.prerequisite_id=? ORDER BY dependent.id
        """,
        todo_id,
    )


def get_todo_fr_links(todo_id: int) -> list[dict[str, Any]]:
    """Return confirmed normalized FR links for a todo."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT todo_id, fr_id, confirmed, created_at FROM todo_fr_links WHERE todo_id=? ORDER BY fr_id",
            (todo_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_related_todos(todo_id: int) -> list[dict[str, Any]]:
    """Return prerequisite and dependent todos, preserving cross-project context."""
    prerequisites = get_required_todos(todo_id)
    dependents = get_required_by_todos(todo_id)
    seen: set[int] = set()
    related: list[dict[str, Any]] = []
    for row in prerequisites + dependents:
        if row["id"] not in seen:
            seen.add(row["id"])
            related.append(row)
    return related


def get_readiness(todo_id: int) -> dict[str, Any]:
    """Explain whether every prerequisite satisfies its edge policy."""
    todo = get_todo_by_id(todo_id)
    if todo is None:
        return {"ready": False, "blocking": [], "explanation": "todo not found"}
    blocking = []
    for prerequisite in get_required_todos(todo_id):
        if prerequisite["closure_reason"] not in prerequisite["allowed_terminal_states"]:
            blocking.append(prerequisite)
    explanation = "ready" if not blocking else "blocked by: " + ", ".join(
        item["text"] for item in blocking
    )
    return {"ready": not blocking, "blocking": blocking, "explanation": explanation}


def can_complete_todo(todo_id: int) -> dict[str, Any]:
    """Return the shared completion-guard result for a todo."""
    readiness = get_readiness(todo_id)
    return {"ready": readiness["ready"], "blocking": readiness["blocking"], "explanation": readiness["explanation"]}


def get_blocking_explanation(todo_id: int) -> str:
    """Return a human-readable prerequisite blocking explanation."""
    return can_complete_todo(todo_id)["explanation"]


def decompose_todo(
    parent_id: int,
    children: Iterable[str | dict[str, Any]],
    inherit_confirmed_fr_link: bool = True,
) -> list[int]:
    """Atomically create implementation-ready children while preserving parent."""
    child_specs = list(children)
    if not child_specs:
        raise ValueError("at least one child is required")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            parent = conn.execute("SELECT * FROM todos WHERE id=?", (parent_id,)).fetchone()
            if parent is None:
                raise ValueError("parent todo not found")
            fr_id = parent["fr_id"] if inherit_confirmed_fr_link else None
            created_at = datetime.now(timezone.utc).isoformat()
            child_ids: list[int] = []
            for spec in child_specs:
                values = spec if isinstance(spec, dict) else {"text": spec}
                text = str(values.get("text", "")).strip()
                if not text:
                    raise ValueError("child text is required")
                cur = conn.execute(
                    """
                    INSERT INTO todos
                        (project, source, text, done, created_at, priority, autonomy_level, fr_id, parent_id)
                    VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        values.get("project", parent["project"]), values.get("source", parent["source"]),
                        text, created_at, values.get("priority", parent["priority"]),
                        values.get("autonomy_level", parent["autonomy_level"]), fr_id, parent_id,
                    ),
                )
                child_id = int(cur.lastrowid)
                child_ids.append(child_id)
                if fr_id:
                    conn.execute(
                        "INSERT INTO todo_fr_links (todo_id, fr_id, confirmed, created_at) VALUES (?, ?, 1, ?)",
                        (child_id, fr_id, created_at),
                    )
            conn.commit()
            return child_ids
        except Exception:
            conn.rollback()
            raise


def link_todo_to_fr(todo_id: int, fr_id: str) -> bool:
    """Link one unlinked todo to a syntactically valid feature request."""
    if not FR_ID_PATTERN.fullmatch(fr_id):
        raise ValueError(f"invalid FR id: {fr_id!r}")
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET fr_id=? WHERE id=? AND fr_id IS NULL",
            (fr_id, todo_id),
        )
        if cur.rowcount == 1:
            conn.execute(
                "INSERT OR IGNORE INTO todo_fr_links (todo_id, fr_id, confirmed, created_at) VALUES (?, ?, 1, ?)",
                (todo_id, fr_id, datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
    return cur.rowcount == 1


def insert_todo(
    project: str,
    source: str,
    text: str,
    autonomy_level: str = "supervised",
    parent_id: int | None = None,
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
                "INSERT INTO todos (project, source, text, done, created_at, autonomy_level, parent_id)"
                " VALUES (?, ?, ?, 0, ?, ?, ?)",
                (project, source, text, created_at, autonomy_level, parent_id),
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
