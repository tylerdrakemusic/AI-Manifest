"""Regression tests for Capital epic/story discovery."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _REPO_ROOT / "tools"


def _load_discover_todos(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(_TOOLS))
    sys.modules.pop("discover_todos", None)
    return importlib.import_module("discover_todos")


def test_capital_scope_is_an_explicit_default_mode_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    monkeypatch.setattr(discover_todos, "init_db", lambda: None)
    monkeypatch.setattr(discover_todos, "get_open_todos", lambda: [])
    monkeypatch.setattr(
        discover_todos,
        "add_todo",
        lambda **kwargs: pytest.fail("dry-run must not insert TODOs"),
    )
    candidates_file = tmp_path / "candidates.json"
    candidates_file.write_text(
        json.dumps([{"project": "capital", "text": "Review picker scoring calibration", "priority": 7}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["discover_todos.py", "--project", "capital", "--candidates-file", str(candidates_file)],
    )

    assert discover_todos.main() == 0
    output = capsys.readouterr().out
    assert "Review picker scoring calibration" in output
    assert "Dry-run only" in output


def test_capital_context_excludes_financial_data_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    monkeypatch.setattr(discover_todos, "init_db", lambda: None)
    monkeypatch.setattr(discover_todos, "get_open_todos", lambda: [])
    monkeypatch.setattr(
        discover_todos,
        "add_todo",
        lambda **kwargs: pytest.fail("dry-run must not insert TODOs"),
    )
    capital_root = tmp_path / "capital"
    capital_root.mkdir()
    (capital_root / "README.md").write_text("benchmark reporting needs drift monitoring", encoding="utf-8")
    holdings_dir = capital_root / "data" / "holdings"
    holdings_dir.mkdir(parents=True)
    (holdings_dir / "private.md").write_text("radio distribution details", encoding="utf-8")
    monkeypatch.setattr(
        discover_todos,
        "PROJECT_ROOTS",
        {**discover_todos.PROJECT_ROOTS, "capital": capital_root},
    )
    monkeypatch.setattr(sys, "argv", ["discover_todos.py", "--project", "capital"])

    assert discover_todos.main() == 0
    output = capsys.readouterr().out
    assert "benchmark observability dashboard" in output.lower()
    assert "public radio distribution" not in output.lower()
    assert "Dry-run only" in output