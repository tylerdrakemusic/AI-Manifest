from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture()
def graph_db(tmp_path, monkeypatch):
    from src.utils import todos_db

    monkeypatch.setattr(todos_db, "DB_PATH", tmp_path / "parent-close.db")
    todos_db.init_db()
    return todos_db


def test_close_todo_tree_recurses_parent_id_and_preserves_closed_descendants(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)
    grandchild = graph_db.insert_todo("workspace", "AI", "Grandchild", parent_id=child)
    closed_child = graph_db.insert_todo("workspace", "AI", "Already closed", parent_id=parent)
    assert graph_db.mark_done(closed_child, force=True) is True

    result = graph_db.close_todo_tree(parent, reason="completed")

    assert result == {
        "root_id": parent,
        "reason": "completed",
        "affected_ids": [parent, child, grandchild],
        "affected_count": 3,
    }
    assert graph_db.get_todo_by_id(closed_child)["closure_reason"] == "completed"


def test_close_todo_tree_does_not_follow_prerequisite_edges(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)
    unrelated = graph_db.insert_todo("workspace", "AI", "Prerequisite")
    unrelated_dependent = graph_db.insert_todo("workspace", "AI", "Unrelated dependent")
    graph_db.link_prerequisite(unrelated_dependent, unrelated)

    result = graph_db.close_todo_tree(parent, reason="cancelled")

    assert result["affected_ids"] == [parent, child]
    assert graph_db.get_todo_by_id(unrelated)["done"] == 0
    assert graph_db.get_todo_by_id(unrelated_dependent)["done"] == 0


def test_close_todo_tree_enforces_readiness_by_default_and_rolls_back(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Blocked parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)
    blocker = graph_db.insert_todo("workspace", "AI", "Blocking prerequisite")
    graph_db.link_prerequisite(parent, blocker)

    with pytest.raises(ValueError, match="readiness"):
        graph_db.close_todo_tree(parent, reason="completed")

    assert graph_db.get_todo_by_id(parent)["done"] == 0
    assert graph_db.get_todo_by_id(child)["done"] == 0


def test_close_todo_tree_requires_trusted_backend_for_force(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Blocked parent")
    blocker = graph_db.insert_todo("workspace", "AI", "Blocking prerequisite")
    graph_db.link_prerequisite(parent, blocker)

    with pytest.raises(PermissionError, match="trusted backend"):
        graph_db.close_todo_tree(parent, reason="completed", force=True)

    result = graph_db.close_todo_tree(
        parent, reason="completed", force=True, trusted_backend=graph_db._TRUSTED_BACKEND
    )
    assert result["affected_ids"] == [parent]


def test_close_todo_tree_rolls_back_when_a_descendant_update_fails(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)
    with graph_db.get_connection() as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_parent_close_child
            BEFORE UPDATE OF done ON todos
            WHEN OLD.id = {child}
            BEGIN
                SELECT RAISE(ABORT, 'injected close failure');
            END
            """.format(child=child),
        )

    with pytest.raises(sqlite3.DatabaseError, match="injected close failure"):
        graph_db.close_todo_tree(parent, reason="cancelled")

    assert graph_db.get_todo_by_id(parent)["done"] == 0
    assert graph_db.get_todo_by_id(child)["done"] == 0


def test_mark_done_closes_open_descendants(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)
    grandchild = graph_db.insert_todo("workspace", "AI", "Grandchild", parent_id=child)

    assert graph_db.mark_done(parent) is True

    for todo_id in (parent, child, grandchild):
        row = graph_db.get_todo_by_id(todo_id)
        assert row["done"] == 1
        assert row["closure_reason"] == "completed"


def test_complete_todo_closes_descendants_and_preserves_root_evidence(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)
    with graph_db.get_connection() as conn:
        conn.execute("UPDATE todos SET updated_at='version-1' WHERE id=?", (parent,))
    version = graph_db.get_todo_by_id(parent)["updated_at"]

    result = graph_db.complete_todo(
        parent, version, "Validated implementation", "proof/test-parent-close.py"
    )

    assert result["completion_evidence"] == "Validated implementation"
    assert result["artifact_reference"] == "proof/test-parent-close.py"
    assert graph_db.get_todo_by_id(child)["closure_reason"] == "completed"


def test_cancel_todo_closes_descendants_without_changing_cancellation_readiness(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Blocked child", parent_id=parent)
    blocker = graph_db.insert_todo("workspace", "AI", "Open prerequisite")
    graph_db.link_prerequisite(child, blocker)

    assert graph_db.cancel_todo(parent) is True

    assert graph_db.get_todo_by_id(parent)["closure_reason"] == "cancelled"
    assert graph_db.get_todo_by_id(child)["closure_reason"] == "cancelled"
    assert graph_db.get_todo_by_id(blocker)["done"] == 0


def test_close_todo_tree_propagates_completion_to_ancestors(graph_db):
    root = graph_db.insert_todo("workspace", "TYLER", "Root")
    parent = graph_db.insert_todo("workspace", "AI", "Parent", parent_id=root)
    completed_sibling = graph_db.insert_todo(
        "workspace", "AI", "Completed sibling", parent_id=parent
    )
    selected_leaf = graph_db.insert_todo("workspace", "AI", "Selected leaf", parent_id=parent)
    cancelled_root_child = graph_db.insert_todo(
        "workspace", "AI", "Cancelled root child", parent_id=root
    )
    assert graph_db.mark_done(completed_sibling) is True
    assert graph_db.cancel_todo(cancelled_root_child) is True

    graph_db.close_todo_tree(selected_leaf, reason="completed")

    for todo_id in (root, parent):
        row = graph_db.get_todo_by_id(todo_id)
        assert row["done"] == 1
        assert row["closure_reason"] == "completed"


def test_open_direct_child_prevents_ancestor_completion(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    completed_child = graph_db.insert_todo("workspace", "AI", "Completed child", parent_id=parent)
    open_child = graph_db.insert_todo("workspace", "AI", "Open child", parent_id=parent)

    assert graph_db.mark_done(completed_child) is True

    parent_row = graph_db.get_todo_by_id(parent)
    assert parent_row["done"] == 0
    assert parent_row["closure_reason"] is None
    assert graph_db.get_todo_by_id(open_child)["done"] == 0


def test_terminal_ancestor_with_open_child_prevents_root_completion(graph_db):
    root = graph_db.insert_todo("workspace", "TYLER", "Root")
    terminal_parent = graph_db.insert_todo(
        "workspace", "AI", "Legacy terminal parent", parent_id=root
    )
    open_grandchild = graph_db.insert_todo(
        "workspace", "AI", "Open grandchild", parent_id=terminal_parent
    )
    completed_sibling = graph_db.insert_todo(
        "workspace", "AI", "Completed sibling", parent_id=terminal_parent
    )
    with graph_db.get_connection() as conn:
        conn.execute(
            """UPDATE todos
               SET done=1, closed_at='legacy-close', closure_reason='completed'
               WHERE id=?""",
            (terminal_parent,),
        )

    assert graph_db.mark_done(completed_sibling) is True

    root_row = graph_db.get_todo_by_id(root)
    assert root_row["done"] == 0
    assert root_row["closure_reason"] is None
    assert graph_db.get_todo_by_id(open_grandchild)["done"] == 0


def test_final_cancelled_child_completes_and_propagates_ancestors(graph_db):
    root = graph_db.insert_todo("workspace", "TYLER", "Root")
    parent = graph_db.insert_todo("workspace", "AI", "Parent", parent_id=root)
    completed_child = graph_db.insert_todo("workspace", "AI", "Completed", parent_id=parent)
    final_child = graph_db.insert_todo("workspace", "AI", "Cancelled", parent_id=parent)
    assert graph_db.mark_done(completed_child) is True

    assert graph_db.cancel_todo(final_child) is True

    for todo_id in (parent, root):
        row = graph_db.get_todo_by_id(todo_id)
        assert row["done"] == 1
        assert row["closure_reason"] == "completed"
    assert graph_db.get_todo_by_id(final_child)["closure_reason"] == "cancelled"


def test_stale_child_does_not_qualify_for_ancestor_completion(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    stale_child = graph_db.insert_todo("workspace", "AI", "Stale child", parent_id=parent)
    final_child = graph_db.insert_todo("workspace", "AI", "Final child", parent_id=parent)
    with graph_db.get_connection() as conn:
        conn.execute(
            "UPDATE todos SET done=1, closure_reason='stale' WHERE id=?", (stale_child,)
        )

    assert graph_db.mark_done(final_child) is True

    assert graph_db.get_todo_by_id(parent)["done"] == 0
    assert graph_db.get_todo_by_id(parent)["closure_reason"] is None


def test_mark_done_rolls_back_when_a_descendant_is_not_ready(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Blocked child", parent_id=parent)
    blocker = graph_db.insert_todo("workspace", "AI", "Open prerequisite")
    graph_db.link_prerequisite(child, blocker)

    assert graph_db.mark_done(parent) is False

    assert graph_db.get_todo_by_id(parent)["done"] == 0
    assert graph_db.get_todo_by_id(child)["done"] == 0


def test_complete_todo_rolls_back_when_a_descendant_is_not_ready(graph_db):
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Blocked child", parent_id=parent)
    blocker = graph_db.insert_todo("workspace", "AI", "Open prerequisite")
    graph_db.link_prerequisite(child, blocker)
    with graph_db.get_connection() as conn:
        conn.execute("UPDATE todos SET updated_at='version-1' WHERE id=?", (parent,))
    version = graph_db.get_todo_by_id(parent)["updated_at"]

    with pytest.raises(ValueError, match="readiness"):
        graph_db.complete_todo(parent, version, "Evidence", "artifact")

    assert graph_db.get_todo_by_id(parent)["done"] == 0
    assert graph_db.get_todo_by_id(child)["done"] == 0