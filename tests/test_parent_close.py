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