"""Focused contracts for the governed todo graph."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def test_init_db_migrates_legacy_todos_to_graph_schema(tmp_path: Path, monkeypatch) -> None:
    from src.utils import todos_db

    db_file = tmp_path / "legacy.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            CREATE TABLE todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('AI', 'TYLER')),
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                priority INTEGER NOT NULL DEFAULT 5,
                fr_id TEXT,
                dependencies TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO todos (project, source, text, created_at, dependencies) VALUES (?, ?, ?, ?, ?)",
            ("workspace", "TYLER", "Preserve dependency text", "2026-08-14T00:00:00+00:00", "vendor API; approval"),
        )

    todos_db.init_db()

    with todos_db.get_connection() as conn:
        todo_columns = {row[1] for row in conn.execute("PRAGMA table_info(todos)")}
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        row = conn.execute(
            "SELECT dependencies, parent_id FROM todos WHERE text=?",
            ("Preserve dependency text",),
        ).fetchone()

    assert "parent_id" in todo_columns
    assert "todo_prerequisites" in tables
    assert "todo_fr_links" in tables
    assert tuple(row) == ("vendor API; approval", None)


@pytest.fixture()
def graph_db(tmp_path: Path, monkeypatch):
    from src.utils import todos_db

    monkeypatch.setattr(todos_db, "DB_PATH", tmp_path / "graph.db")
    todos_db.init_db()
    return todos_db


def test_prerequisite_queries_and_default_terminal_policy(graph_db) -> None:
    prerequisite = graph_db.insert_todo("life", "AI", "Obtain lab result")
    dependent = graph_db.insert_todo("workspace", "TYLER", "Review result")

    assert graph_db.link_prerequisite(dependent, prerequisite) is True
    assert [row["id"] for row in graph_db.get_required_todos(dependent)] == [prerequisite]
    assert [row["id"] for row in graph_db.get_required_by_todos(prerequisite)] == [dependent]
    assert graph_db.get_readiness(dependent)["ready"] is False
    assert graph_db.get_readiness(dependent)["blocking"][0]["id"] == prerequisite

    assert graph_db.cancel_todo(prerequisite) is True
    assert graph_db.get_readiness(dependent)["ready"] is True
    assert graph_db.mark_done(dependent) is True


def test_edge_policy_can_narrow_terminal_states(graph_db) -> None:
    prerequisite = graph_db.insert_todo("workspace", "AI", "Optional review")
    dependent = graph_db.insert_todo("workspace", "AI", "Publish review")
    graph_db.link_prerequisite(dependent, prerequisite, allowed_terminal_states={"completed"})

    assert graph_db.cancel_todo(prerequisite) is True
    readiness = graph_db.get_readiness(dependent)
    assert readiness["ready"] is False
    assert readiness["blocking"][0]["allowed_terminal_states"] == ["completed"]


def test_link_prerequisite_rejects_cycles(graph_db) -> None:
    first = graph_db.insert_todo("workspace", "AI", "First")
    second = graph_db.insert_todo("workspace", "AI", "Second")
    graph_db.link_prerequisite(second, first)

    with pytest.raises(ValueError, match="cycle"):
        graph_db.link_prerequisite(first, second)


def test_parent_completion_is_independent_of_child_completion(graph_db) -> None:
    parent = graph_db.insert_todo("workspace", "TYLER", "Parent")
    child = graph_db.insert_todo("workspace", "AI", "Child", parent_id=parent)

    assert graph_db.mark_done(parent) is True
    assert graph_db.get_todo_by_id(child)["done"] == 0


def test_decompose_preserves_parent_and_inherits_confirmed_fr_link(graph_db) -> None:
    parent = graph_db.insert_todo("workspace", "TYLER", "Implement graph")
    assert graph_db.link_todo_to_fr(parent, "FR-20260814-governed-todo-graph") is True

    children = graph_db.decompose_todo(
        parent,
        ["Add schema", "Add graph queries", "Add completion guard"],
    )

    assert len(children) == 3
    assert graph_db.get_todo_by_id(parent)["done"] == 0
    assert all(graph_db.get_todo_by_id(child)["parent_id"] == parent for child in children)
    assert all(graph_db.get_todo_by_id(child)["fr_id"] == "FR-20260814-governed-todo-graph" for child in children)
    assert {row["id"] for row in graph_db.get_required_by_todos(parent)} == set()


def test_completion_guard_explains_blocking_prerequisite(graph_db) -> None:
    prerequisite = graph_db.insert_todo("workspace", "AI", "Blocked prerequisite")
    dependent = graph_db.insert_todo("workspace", "AI", "Guarded dependent")
    graph_db.link_prerequisite(dependent, prerequisite)

    assert graph_db.mark_done(dependent) is False
    assert "Blocked prerequisite" in graph_db.get_blocking_explanation(dependent)


def test_cross_project_graph_and_cross_fr_links_are_queryable(graph_db) -> None:
    prerequisite = graph_db.insert_todo("life", "AI", "Life deliverable")
    dependent = graph_db.insert_todo("music", "TYLER", "Music deliverable")
    assert graph_db.link_todo_to_fr(prerequisite, "FR-20260814-life-link") is True
    assert graph_db.link_todo_to_fr(dependent, "FR-20260814-music-link") is True
    graph_db.link_prerequisite(dependent, prerequisite)

    links = graph_db.get_todo_fr_links(dependent)
    related = graph_db.get_related_todos(dependent)
    assert links[0]["fr_id"] == "FR-20260814-music-link"
    assert related[0]["project"] == "life"
    assert related[0]["fr_id"] == "FR-20260814-life-link"