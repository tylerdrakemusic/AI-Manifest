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


def test_public_create_todo_forwards_optional_context_fields(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = mcp_server.create_todo(
        project="workspace",
        text="Create with context",
        rationale="Clarify why this work matters",
        implementation_hints="Start with the coordination wrapper",
        context_snapshot="The DB helper already accepts rich fields",
        estimated_effort="S",
        dependencies="FR-20260829-parent",
    )

    todo = todos_db.get_todo_by_id(todo_id)
    assert todo["rationale"] == "Clarify why this work matters"
    assert todo["implementation_hints"] == "Start with the coordination wrapper"
    assert todo["context_snapshot"] == "The DB helper already accepts rich fields"
    assert todo["estimated_effort"] == "S"
    assert todo["dependencies"] == "FR-20260829-parent"


def test_public_create_todo_rich_fields_round_trip_through_public_read(tmp_db):
    from src.integrations.coordination import mcp_server

    values = {
        "rationale": "Clarify why this work matters",
        "implementation_hints": "Start with the coordination wrapper",
        "context_snapshot": "The DB helper already accepts rich fields",
        "estimated_effort": "S",
        "dependencies": "FR-20260829-parent",
    }

    todo_id = mcp_server.create_todo(
        project="workspace",
        text="Read context through the public wrapper",
        **values,
    )

    todo = mcp_server.read_todo(todo_id)
    assert {field: todo[field] for field in values} == values


def test_public_create_todo_omitted_rich_fields_read_as_none(tmp_db):
    from src.integrations.coordination import mcp_server

    todo_id = mcp_server.create_todo(
        project="workspace",
        text="Create without optional context",
    )

    todo = mcp_server.read_todo(todo_id)
    assert all(
        todo[field] is None
        for field in (
            "rationale",
            "implementation_hints",
            "context_snapshot",
            "estimated_effort",
            "dependencies",
        )
    )


def test_public_create_todo_rejects_integer_confirmation_with_rich_fields(tmp_db):
    from src.integrations.coordination import mcp_server

    with pytest.raises(PermissionError, match="confirmation is required"):
        mcp_server.create_todo(
            project="workspace",
            text="Reject non-literal confirmation",
            rationale="Should not be written",
            implementation_hints="Should not be written",
            context_snapshot="Should not be written",
            estimated_effort="S",
            dependencies="FR-20260829-parent",
            confirmed=1,
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


def test_nested_metadata_payload_uses_one_canonical_supported_field_set(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todo_decision_contract, todos_db

    assert "primary_benefit_category" in todo_decision_contract.SUPPORTED_FIELDS

    todo_id = todos_db.add_todo("workspace", "Nested metadata target")
    metadata = {
        "expected_value": 5,
        "user_or_system_benefit": 5,
        "strategic_alignment": 5,
        "confidence": 5,
        "cost_of_delay": 5,
        "primary_benefit_category": "system",
        "benefit_summary": "Makes the decision explicit",
        "justification": "The nested MCP object is the canonical payload",
        "evidence": ["FR acceptance criteria"],
    }

    mcp_server.invoke_todo_operation(
        "todo.set_decision_metadata",
        {"todo_id": todo_id, "metadata": metadata, "assessed_by": "test", "confirmed": True},
    )

    assert mcp_server.invoke_todo_operation(
        "todo.get_decision_metadata", {"todo_id": todo_id}
    )["primary_benefit_category"] == "system"


def test_invalid_nested_metadata_does_not_write_or_append_assessment(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = todos_db.add_todo("workspace", "Invalid nested metadata")
    metadata = {
        "expected_value": 5,
        "user_or_system_benefit": 5,
        "strategic_alignment": 5,
        "confidence": 5,
        "cost_of_delay": 5,
        "primary_benefit_category": "unsupported",
        "benefit_summary": "Should not persist",
        "justification": "The category is invalid",
        "evidence": ["test"],
    }

    with pytest.raises(ValueError, match="primary_benefit_category"):
        mcp_server.invoke_todo_operation(
            "todo.set_decision_metadata",
            {"todo_id": todo_id, "metadata": metadata, "assessed_by": "test", "confirmed": True},
        )

    assert mcp_server.invoke_todo_operation(
        "todo.get_decision_metadata", {"todo_id": todo_id}
    ) is None
    assert mcp_server.invoke_todo_operation(
        "todo.get_decision_assessments", {"todo_id": todo_id}
    ) == []


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


def test_authenticated_rich_update_requires_version_and_preserves_protected_fields(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    todo_id = todos_db.add_todo("workspace", "Original", priority=4)
    original = todos_db.get_todo_by_id(todo_id)

    with pytest.raises(PermissionError, match="authentication"):
        mcp_server.invoke_todo_operation(
            "todo.update",
            {"todo_id": todo_id, "text": "Updated", "authenticated": False},
        )

    updated = mcp_server.invoke_todo_operation(
        "todo.update",
        {
            "todo_id": todo_id,
            "text": "Updated",
            "rationale": "More context",
            "expected_version": original["updated_at"],
            "authenticated": True,
        },
    )

    assert updated["text"] == "Updated"
    assert updated["rationale"] == "More context"
    assert updated["id"] == todo_id
    assert updated["project"] == original["project"]
    assert updated["created_at"] == original["created_at"]
    assert updated["updated_at"] != original["updated_at"]

    with pytest.raises(ValueError, match="precondition"):
        mcp_server.invoke_todo_operation(
            "todo.update",
            {
                "todo_id": todo_id,
                "text": "Stale",
                "expected_version": original["updated_at"],
                "authenticated": True,
            },
        )


def test_child_batch_is_idempotent_and_graph_read_is_complete(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    parent_id = todos_db.add_todo("workspace", "Parent", priority=6)
    payload = {
        "parent_id": parent_id,
        "children": [
            {"text": "First"},
            {"text": "Second", "prerequisite_indices": [0]},
        ],
        "confirmed": True,
        "idempotency_key": "batch-1",
    }
    child_ids = mcp_server.invoke_todo_operation("todo.create_children_batch", payload)
    assert mcp_server.invoke_todo_operation("todo.create_children_batch", payload) == child_ids
    assert todos_db.get_todo_by_id(child_ids[0])["priority"] == 6

    graph = mcp_server.invoke_todo_operation("todo.graph", {"todo_id": parent_id})
    assert [child["id"] for child in graph["children"]] == child_ids
    assert graph["children"][1]["parent_id"] == parent_id


def test_confirmed_decompose_allows_priority_override(tmp_db):
    from src.integrations.coordination import mcp_server
    from src.utils import todos_db

    parent_id = todos_db.add_todo("workspace", "Parent", priority=5)
    child_ids = mcp_server.invoke_todo_operation(
        "todo.decompose",
        {
            "parent_id": parent_id,
            "children": [{"text": "Escalated child", "priority": 9}],
            "confirmed": True,
        },
    )

    assert todos_db.get_todo_by_id(child_ids[0])["priority"] == 9