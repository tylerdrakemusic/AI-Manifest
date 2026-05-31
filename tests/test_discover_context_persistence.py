"""RED phase: context fields persist end-to-end through add_todo() and Candidate.

AC-6: add_todo() accepts and persists all 5 context fields.
AC-3: _discovery_prompt returns JSON with new keys (covered via Candidate shape).
AC-5: Candidate dataclass carries all 5 fields (printed in approval table).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS = str(_REPO_ROOT / "tools")

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DB_PATH to a temp file for each test."""
    db_file = tmp_path / "test_todos.db"
    import src.utils.todos_db as todos_db
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    todos_db.init_db()
    return db_file


# ---------------------------------------------------------------------------
# add_todo() context field persistence
# ---------------------------------------------------------------------------

def test_add_todo_persists_all_context_fields(tmp_db: Path) -> None:
    """add_todo() must INSERT all 5 context fields into the DB."""
    import src.utils.todos_db as todos_db
    tid = todos_db.add_todo(
        project="music",
        text="Ship public radio launch",
        priority=8,
        source="TYLER",
        autonomy_level="human",
        rationale="High visibility launch needed",
        implementation_hints="Start with Brand/ARTIST_PROFILE.json",
        context_snapshot="Brand has 3 active channels; no radio yet",
        estimated_effort="L",
        dependencies="FR-001,FR-002",
    )
    row = todos_db.get_todo_by_id(tid)
    assert row is not None
    assert row["rationale"] == "High visibility launch needed"
    assert row["implementation_hints"] == "Start with Brand/ARTIST_PROFILE.json"
    assert row["context_snapshot"] == "Brand has 3 active channels; no radio yet"
    assert row["estimated_effort"] == "L"
    assert row["dependencies"] == "FR-001,FR-002"


def test_get_open_todos_returns_context_fields(tmp_db: Path) -> None:
    """get_open_todos() must include the 5 context fields in returned dicts."""
    import src.utils.todos_db as todos_db
    todos_db.add_todo(
        project="quantum",
        text="Benchmark QPU telemetry",
        priority=6,
        source="AI",
        autonomy_level="full",
        rationale="Need telemetry baseline",
        implementation_hints="Use existing benchmark harness",
        context_snapshot="Last run 2 weeks ago",
        estimated_effort="M",
        dependencies="",
    )
    rows = todos_db.get_open_todos(project="quantum")
    assert len(rows) >= 1
    first = rows[0]
    assert first["rationale"] == "Need telemetry baseline"
    assert first["estimated_effort"] == "M"


def test_add_todo_context_fields_default_to_none(tmp_db: Path) -> None:
    """add_todo() without context keyword args must store NULL for those columns."""
    import src.utils.todos_db as todos_db
    tid = todos_db.add_todo(
        project="workspace",
        text="No context todo",
        priority=3,
    )
    row = todos_db.get_todo_by_id(tid)
    assert row is not None
    assert row["rationale"] is None
    assert row["estimated_effort"] is None


# ---------------------------------------------------------------------------
# Candidate dataclass
# ---------------------------------------------------------------------------

def test_candidate_dataclass_carries_context_fields() -> None:
    """Candidate must have all 5 new context fields."""
    if "discover_todos" in sys.modules:
        del sys.modules["discover_todos"]
    import discover_todos
    c = discover_todos.Candidate(
        project="workspace",
        text="Test candidate",
        priority=5,
        similar_to=None,
        rationale="test rationale",
        implementation_hints="test hints",
        context_snapshot="test snapshot",
        estimated_effort="XS",
        dependencies="",
    )
    assert c.rationale == "test rationale"
    assert c.implementation_hints == "test hints"
    assert c.context_snapshot == "test snapshot"
    assert c.estimated_effort == "XS"
    assert c.dependencies == ""


def test_candidate_dataclass_context_fields_default_empty() -> None:
    """Candidate must work without context fields (backward-compat)."""
    if "discover_todos" in sys.modules:
        del sys.modules["discover_todos"]
    import discover_todos
    c = discover_todos.Candidate(
        project="workspace",
        text="Minimal candidate",
        priority=5,
        similar_to=None,
    )
    assert c.rationale == ""
    assert c.implementation_hints == ""
    assert c.estimated_effort == ""
    assert c.dependencies == ""
