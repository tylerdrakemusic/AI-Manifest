"""RED phase: 5 new rich-context columns in todos schema.

AC-2: Schema migration — idempotent, 5 nullable TEXT columns added.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_NEW_COLUMNS = [
    "rationale",
    "implementation_hints",
    "context_snapshot",
    "estimated_effort",
    "dependencies",
]


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DB_PATH to a temp file for each test."""
    db_file = tmp_path / "test_todos.db"
    import src.utils.todos_db as todos_db
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    return db_file


def _col_names(conn, table: str = "todos") -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


# ---------------------------------------------------------------------------
# Column presence after init_db()
# ---------------------------------------------------------------------------

def test_init_db_adds_five_context_columns(tmp_db: Path) -> None:
    """init_db() must add all 5 rich-context columns."""
    import src.utils.todos_db as todos_db
    todos_db.init_db()
    conn = todos_db.get_connection()
    cols = _col_names(conn)
    for col in _NEW_COLUMNS:
        assert col in cols, f"Column '{col}' missing after init_db()"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_init_db_idempotent_with_context_columns(tmp_db: Path) -> None:
    """Calling init_db() twice must not raise (ALTER TABLE guarded by PRAGMA)."""
    import src.utils.todos_db as todos_db
    todos_db.init_db()
    todos_db.init_db()  # must not raise


# ---------------------------------------------------------------------------
# Round-trip with all 5 context fields
# ---------------------------------------------------------------------------

def test_context_fields_roundtrip(tmp_db: Path) -> None:
    """A todo inserted with all 5 context fields should be retrievable intact."""
    import src.utils.todos_db as todos_db
    todos_db.init_db()
    tid = todos_db.add_todo(
        project="workspace",
        text="Rich context test todo",
        priority=5,
        source="AI",
        autonomy_level="full",
        rationale="Surfaced because backlog is stale",
        implementation_hints="Start in todos_db.py add_todo()",
        context_snapshot="workspace has 80 open todos, last discovery 5 days ago",
        estimated_effort="S",
        dependencies="FR-20260530",
    )
    row = todos_db.get_todo_by_id(tid)
    assert row is not None
    assert row["rationale"] == "Surfaced because backlog is stale"
    assert row["implementation_hints"] == "Start in todos_db.py add_todo()"
    assert row["context_snapshot"] == "workspace has 80 open todos, last discovery 5 days ago"
    assert row["estimated_effort"] == "S"
    assert row["dependencies"] == "FR-20260530"
