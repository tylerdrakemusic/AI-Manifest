from __future__ import annotations

import pytest
import subprocess
import sys
from pathlib import Path


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    db_file = tmp_path / "todos.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    monkeypatch.setattr(mcp_server, "_REPO_ROOT", tmp_path)
    todos_db.init_db()
    return db_file


def test_link_todo_to_fr_requires_explicit_confirmation(monkeypatch):
    from src.integrations.coordination.mcp_server import link_todo_to_fr

    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(
        "src.integrations.coordination.mcp_server.todos_db.link_todo_to_fr",
        lambda todo_id, fr_id: calls.append((todo_id, fr_id)) or True,
    )

    with pytest.raises(PermissionError, match="confirmation is required"):
        link_todo_to_fr(7, "FR-20260809-example", confirmed=False)

    assert calls == []


def test_link_todo_to_fr_delegates_only_after_confirmation(monkeypatch):
    from src.integrations.coordination.mcp_server import link_todo_to_fr

    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(
        "src.integrations.coordination.mcp_server.todos_db.link_todo_to_fr",
        lambda todo_id, fr_id: calls.append((todo_id, fr_id)) or True,
    )

    assert link_todo_to_fr(7, "FR-20260809-example", confirmed=True) is True
    assert calls == [(7, "FR-20260809-example")]


def test_todo_operation_rejects_arbitrary_database_and_sql_inputs():
    from src.integrations.coordination.mcp_server import invoke_todo_operation

    with pytest.raises(ValueError, match="database and SQL arguments are not supported"):
        invoke_todo_operation(
            "todo.link_fr",
            {
                "todo_id": 7,
                "fr_id": "FR-20260809-example",
                "confirmed": True,
                "db": "infinitelife",
            },
        )

    with pytest.raises(ValueError, match="unsupported todo operation"):
        invoke_todo_operation("db.write_query", {})


def test_confirmed_link_updates_only_the_selected_todo(tmp_db):
    from src.integrations.coordination.mcp_server import link_todo_to_fr
    from src.utils import todos_db

    todo_id = todos_db.insert_todo("workspace", "TYLER", "Coordinate MCP")

    assert link_todo_to_fr(todo_id, "FR-20260809-example", confirmed=True) is True
    todo = todos_db.get_todo_by_id(todo_id)
    assert todo["fr_id"] == "FR-20260809-example"


def test_link_rejects_invalid_fr_id_and_does_not_write(tmp_db):
    from src.integrations.coordination.mcp_server import link_todo_to_fr
    from src.utils import todos_db

    todo_id = todos_db.insert_todo("workspace", "TYLER", "Reject bad linkage")

    with pytest.raises(ValueError, match="invalid FR id"):
        link_todo_to_fr(todo_id, "not-a-fr", confirmed=True)
    assert todos_db.get_todo_by_id(todo_id)["fr_id"] is None


def test_link_does_not_overwrite_existing_fr_id(tmp_db):
    from src.integrations.coordination.mcp_server import link_todo_to_fr
    from src.utils import todos_db

    todo_id = todos_db.insert_todo("workspace", "TYLER", "Keep first linkage")
    assert link_todo_to_fr(todo_id, "FR-20260809-first", confirmed=True) is True

    assert link_todo_to_fr(todo_id, "FR-20260809-second", confirmed=True) is False
    assert todos_db.get_todo_by_id(todo_id)["fr_id"] == "FR-20260809-first"


def test_mcp_module_loads_by_absolute_path_from_outside_repo(tmp_path):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "integrations"
        / "coordination"
        / "mcp_server.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy, sys; runpy.run_path(sys.argv[1])",
            module_path,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr


def test_mcp_server_exports_fast_mcp():
    from src.integrations.coordination.mcp_server import FastMCP

    assert FastMCP.__name__ == "FastMCP"


def test_list_open_todos_initializes_canonical_db_in_fresh_worktree(tmp_path, monkeypatch):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    fresh_db = tmp_path / "src" / "data" / "manifest_todos.db"
    monkeypatch.setattr(todos_db, "DB_PATH", fresh_db)
    monkeypatch.setattr(mcp_server, "_REPO_ROOT", tmp_path)

    assert not fresh_db.exists()
    assert mcp_server.invoke_todo_operation("todo.list_open", {}) == []

    with todos_db.get_connection() as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='todos'"
        ).fetchone()
    assert table is not None


def test_mcp_graph_read_operations_are_allowlisted(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    prerequisite = todos_db.insert_todo("life", "AI", "Graph prerequisite")
    dependent = todos_db.insert_todo("workspace", "AI", "Graph dependent")
    assert mcp_server.invoke_todo_operation(
        "todo.link_prerequisite",
        {"todo_id": dependent, "prerequisite_id": prerequisite, "confirmed": True},
    ) is True
    result = mcp_server.invoke_todo_operation("todo.readiness", {"todo_id": dependent})
    assert result["ready"] is False
    assert mcp_server.invoke_todo_operation("todo.related", {"todo_id": dependent})[0]["id"] == prerequisite
    assert mcp_server.invoke_todo_operation("todo.fr_links", {"todo_id": dependent}) == []


def test_mcp_graph_mutations_require_confirmation(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    prerequisite = todos_db.insert_todo("life", "AI", "Needs approval")
    dependent = todos_db.insert_todo("workspace", "AI", "Wait for approval")
    with pytest.raises(PermissionError, match="confirmation is required"):
        mcp_server.invoke_todo_operation(
            "todo.link_prerequisite",
            {"todo_id": dependent, "prerequisite_id": prerequisite},
        )


def test_todo_create_defaults_priority_and_rejects_unconfirmed_explicit_priority(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = mcp_server.invoke_todo_operation(
        "todo.create",
        {"project": "workspace", "text": "Default priority"},
    )
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 5

    with pytest.raises(PermissionError, match="confirmation is required"):
        mcp_server.invoke_todo_operation(
            "todo.create",
            {"project": "workspace", "text": "Explicit priority", "priority": 8},
        )


def test_todo_read_and_draft_scope_are_allowlisted(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = todos_db.add_todo("workspace", "Read me")
    assert mcp_server.invoke_todo_operation("todo.read", {"todo_id": todo_id})["id"] == todo_id
    assert mcp_server.invoke_todo_operation(
        "todo.draft_scope", {"todo_id": todo_id, "scope": "tests only"}
    ) == {"todo_id": todo_id, "scope": "tests only", "draft": True}


def test_metadata_operations_validate_append_history_and_leave_todo_fields_unchanged(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = todos_db.add_todo("workspace", "Metadata target", priority=4)
    metadata = {
        "expected_value": 8,
        "user_or_system_benefit": 7,
        "strategic_alignment": 8,
        "confidence": 7,
        "cost_of_delay": 7,
        "primary_benefit_category": "system",
        "benefit_summary": "Makes the decision explicit",
        "justification": "The coordination path needs an audit trail",
        "evidence": ["FR acceptance criteria"],
    }

    with pytest.raises(PermissionError, match="confirmation is required"):
        mcp_server.invoke_todo_operation(
            "todo.set_decision_metadata",
            {"todo_id": todo_id, "metadata": metadata, "assessed_by": "test", "confirmed": 1},
        )

    mcp_server.invoke_todo_operation(
        "todo.set_decision_metadata",
        {"todo_id": todo_id, "metadata": metadata, "assessed_by": "test", "confirmed": True},
    )
    assert mcp_server.invoke_todo_operation("todo.get_decision_metadata", {"todo_id": todo_id})["confidence"] == 7
    assert len(mcp_server.invoke_todo_operation("todo.get_decision_assessments", {"todo_id": todo_id})) == 1
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 4


def test_priority_guidance_is_advisory_and_priority_change_requires_confirmation(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = todos_db.add_todo("workspace", "Priority target", priority=4)
    guidance = mcp_server.invoke_todo_operation("todo.priority_guidance", {"todo_id": todo_id})
    assert guidance["advisory"] is True
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 4

    with pytest.raises(PermissionError, match="confirmation is required"):
        mcp_server.invoke_todo_operation(
            "todo.set_priority", {"todo_id": todo_id, "priority": 9}
        )
    assert mcp_server.invoke_todo_operation(
        "todo.set_priority", {"todo_id": todo_id, "priority": 9, "confirmed": True}
    ) is True
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 9


def test_new_todo_operations_reject_arbitrary_database_and_sql_inputs(tmp_db):
    from src.integrations.coordination.mcp_server import invoke_todo_operation

    with pytest.raises(ValueError, match="database and SQL arguments are not supported"):
        invoke_todo_operation("todo.read", {"todo_id": 1, "sql": "DROP TABLE todos"})