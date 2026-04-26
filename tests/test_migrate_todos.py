"""Tests for migrate_todos — idempotent flat-file → DB migration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_todo_files(root: Path, ai_items: list[str], tyler_items: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    ai_lines = ["# AI Tasks\n"] + [f"- [ ] {item}\n" for item in ai_items]
    (root / "TODO_AI.md").write_text("".join(ai_lines), encoding="utf-8")
    tyler_lines = ["# Tyler Tasks\n"] + [f"- [ ] {item}\n" for item in tyler_items]
    (root / "TODO_TYLER.md").write_text("".join(tyler_lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DB_PATH and TODO_SOURCES to temp dirs."""
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    db_file = tmp_path / "data" / "manifest_todos.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)

    # Build temp project roots with known content
    music_root = tmp_path / "Music"
    life_root = tmp_path / "Life"
    _write_todo_files(music_root, ["Music AI task 1", "Music AI task 2"], ["Music Tyler task"])
    _write_todo_files(life_root, ["Life AI task"], [])

    fake_sources = [
        {"key": "music", "root": music_root},
        {"key": "life",  "root": life_root},
    ]
    monkeypatch.setattr(migrate_todos, "TODO_SOURCES", fake_sources)

    todos_db.init_db()
    yield {"db_file": db_file, "music_root": music_root, "life_root": life_root}


# ---------------------------------------------------------------------------
# migrate() — dry run
# ---------------------------------------------------------------------------

def test_dry_run_does_not_create_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    db_file = tmp_path / "data" / "no_create.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)

    music_root = tmp_path / "Music"
    _write_todo_files(music_root, ["Dry run task"], [])
    monkeypatch.setattr(migrate_todos, "TODO_SOURCES", [{"key": "music", "root": music_root}])

    migrate_todos.migrate(dry_run=True)
    assert not db_file.exists(), "DB should NOT be created during a dry run"


def test_dry_run_does_not_remove_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    db_file = tmp_path / "data" / "no_remove.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)

    music_root = tmp_path / "Music"
    _write_todo_files(music_root, ["Keep me"], [])
    monkeypatch.setattr(migrate_todos, "TODO_SOURCES", [{"key": "music", "root": music_root}])

    migrate_todos.migrate(dry_run=True)
    assert (music_root / "TODO_AI.md").exists(), "Flat file should survive a dry run"


# ---------------------------------------------------------------------------
# migrate() — real run
# ---------------------------------------------------------------------------

def test_migrate_inserts_correct_count(isolated_env: dict) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    result = migrate_todos.migrate(dry_run=False)
    # Music: 2 AI + 1 Tyler = 3; Life: 1 AI + 0 Tyler = 1 → total 4
    assert result["inserted"] == 4
    assert result["skipped"] == 0


def test_migrate_todos_in_db(isolated_env: dict) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    migrate_todos.migrate(dry_run=False)
    open_todos = todos_db.get_open_todos()
    texts = {t["text"] for t in open_todos}
    assert "Music AI task 1" in texts
    assert "Music Tyler task" in texts
    assert "Life AI task" in texts


def test_migrate_sources_labelled_correctly(isolated_env: dict) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    migrate_todos.migrate(dry_run=False)
    open_todos = todos_db.get_open_todos()
    sources = {(t["project"], t["source"]) for t in open_todos}
    assert ("music", "AI") in sources
    assert ("music", "TYLER") in sources
    assert ("life", "AI") in sources


def test_migrate_removes_flat_files(isolated_env: dict) -> None:
    import tools.migrate_todos as migrate_todos

    migrate_todos.migrate(dry_run=False)
    assert not (isolated_env["music_root"] / "TODO_AI.md").exists()
    assert not (isolated_env["music_root"] / "TODO_TYLER.md").exists()
    assert not (isolated_env["life_root"] / "TODO_AI.md").exists()


def test_migrate_idempotent(isolated_env: dict) -> None:
    """Re-running migration skips duplicate rows without error."""
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    # First run
    migrate_todos.migrate(dry_run=False)
    count_after_first = todos_db.count_todos()

    # Restore flat files so second run has something to read
    _write_todo_files(
        isolated_env["music_root"],
        ["Music AI task 1", "Music AI task 2"],
        ["Music Tyler task"],
    )
    _write_todo_files(isolated_env["life_root"], ["Life AI task"], [])

    # Second run — should skip all (duplicates), not raise
    result2 = migrate_todos.migrate(dry_run=False)
    assert result2["inserted"] == 0
    assert result2["skipped"] == 4
    assert todos_db.count_todos() == count_after_first


# ---------------------------------------------------------------------------
# auto_migrate_if_needed
# ---------------------------------------------------------------------------

def test_auto_migrate_runs_when_db_empty(isolated_env: dict) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    ran = migrate_todos.auto_migrate_if_needed()
    assert ran is True
    assert todos_db.count_todos() > 0


def test_auto_migrate_skips_when_db_has_data(isolated_env: dict) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    # Seed one row manually
    todos_db.insert_todo("music", "AI", "Pre-existing")
    ran = migrate_todos.auto_migrate_if_needed()
    assert ran is False


def test_auto_migrate_skips_when_no_flat_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.utils.todos_db as todos_db
    import tools.migrate_todos as migrate_todos

    db_file = tmp_path / "data" / "empty.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    monkeypatch.setattr(migrate_todos, "TODO_SOURCES", [
        {"key": "music", "root": tmp_path / "no_such_dir"},
    ])
    todos_db.init_db()

    ran = migrate_todos.auto_migrate_if_needed()
    assert ran is False
