"""Tests for todos_db — binary done/not-done todo card DB."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DB_PATH to a temp file for each test."""
    db_file = tmp_path / "test_todos.db"
    import src.utils.todos_db as todos_db
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    todos_db.init_db()
    yield db_file


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_table(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    conn = todos_db.get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='todos'"
    ).fetchone()
    assert row is not None, "todos table should exist after init_db()"


def test_init_db_idempotent(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    todos_db.init_db()  # second call should not raise
    todos_db.init_db()


def test_init_db_adds_nullable_perfected_at_without_losing_existing_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.utils.todos_db as todos_db

    db_file = tmp_path / "legacy_todos.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute("""
            CREATE TABLE todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                source TEXT NOT NULL CHECK(source IN ('AI', 'TYLER')),
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                priority INTEGER NOT NULL DEFAULT 5,
                autonomy_level TEXT NOT NULL DEFAULT 'supervised',
                fr_id TEXT
            )
        """)
        conn.execute(
            "INSERT INTO todos (id, project, source, text, created_at, fr_id) VALUES (?, ?, ?, ?, ?, ?)",
            (227, "workspace", "TYLER", "Preserve this todo", "2026-08-09T00:00:00+00:00", "FR-20260809-todo-provenance-signal-rail"),
        )

    todos_db.init_db()

    with todos_db.get_connection() as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(todos)")}
        row = conn.execute("SELECT id, fr_id, perfected_at FROM todos WHERE id=227").fetchone()
    assert columns["perfected_at"][3] == 0
    assert tuple(row) == (227, "FR-20260809-todo-provenance-signal-rail", None)


# ---------------------------------------------------------------------------
# insert_todo
# ---------------------------------------------------------------------------

def test_insert_todo_returns_id(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    row_id = todos_db.insert_todo("music", "AI", "Write tests")
    assert isinstance(row_id, int)
    assert row_id > 0


def test_insert_todo_duplicate_returns_none(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    todos_db.insert_todo("music", "AI", "Deduped item")
    result = todos_db.insert_todo("music", "AI", "Deduped item")
    assert result is None


def test_insert_todo_different_project_not_duplicate(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    id1 = todos_db.insert_todo("music", "AI", "Same text")
    id2 = todos_db.insert_todo("life", "AI", "Same text")
    assert id1 is not None
    assert id2 is not None
    assert id1 != id2


def test_insert_todo_different_source_not_duplicate(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    id1 = todos_db.insert_todo("music", "AI", "Same text")
    id2 = todos_db.insert_todo("music", "TYLER", "Same text")
    assert id1 is not None
    assert id2 is not None


# ---------------------------------------------------------------------------
# get_open_todos / get_done_todos
# ---------------------------------------------------------------------------

def test_get_open_todos_all_projects(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    todos_db.insert_todo("music", "AI", "Task A")
    todos_db.insert_todo("life", "TYLER", "Task B")
    open_todos = todos_db.get_open_todos()
    assert len(open_todos) == 2
    projects = {t["project"] for t in open_todos}
    assert projects == {"music", "life"}


def test_get_open_todos_filtered_by_project(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    todos_db.insert_todo("music", "AI", "Music task")
    todos_db.insert_todo("life", "AI", "Life task")
    music_todos = todos_db.get_open_todos("music")
    assert len(music_todos) == 1
    assert music_todos[0]["project"] == "music"


def test_get_done_todos_empty_initially(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    todos_db.insert_todo("music", "AI", "New task")
    done = todos_db.get_done_todos()
    assert len(done) == 0


def test_get_done_todos_after_mark_done(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    row_id = todos_db.insert_todo("music", "AI", "To close")
    todos_db.mark_done(row_id)
    done = todos_db.get_done_todos()
    assert len(done) == 1
    assert done[0]["project"] == "music"


# ---------------------------------------------------------------------------
# mark_done
# ---------------------------------------------------------------------------

def test_mark_done_returns_true_on_success(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    row_id = todos_db.insert_todo("quantum", "AI", "Close me")
    assert todos_db.mark_done(row_id) is True


def test_mark_done_removes_from_open(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    row_id = todos_db.insert_todo("quantum", "AI", "Will be closed")
    todos_db.mark_done(row_id)
    open_todos = todos_db.get_open_todos()
    assert all(t["id"] != row_id for t in open_todos)


def test_mark_done_sets_closed_at(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    row_id = todos_db.insert_todo("quantum", "AI", "Check timestamp")
    todos_db.mark_done(row_id)
    done = todos_db.get_done_todos()
    assert done[0]["closed_at"] is not None


def test_mark_done_already_done_returns_false(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    row_id = todos_db.insert_todo("workspace", "AI", "Close twice")
    todos_db.mark_done(row_id)
    assert todos_db.mark_done(row_id) is False


def test_mark_done_nonexistent_id_returns_false(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    assert todos_db.mark_done(99999) is False


# ---------------------------------------------------------------------------
# count_todos
# ---------------------------------------------------------------------------

def test_count_todos_includes_open_and_done(tmp_db: Path) -> None:
    import src.utils.todos_db as todos_db
    id1 = todos_db.insert_todo("music", "AI", "Open one")
    id2 = todos_db.insert_todo("music", "AI", "Done one")
    todos_db.mark_done(id2)
    assert todos_db.count_todos() == 2
