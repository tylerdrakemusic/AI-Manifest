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


def test_default_project_selection_is_unchanged_without_project(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    selected_projects: list[list[str]] = []
    monkeypatch.setattr(discover_todos, "init_db", lambda: None)
    monkeypatch.setattr(
        discover_todos,
        "_prepare_candidates",
        lambda projects, limit, candidates_file=None: selected_projects.append(projects) or [],
    )
    monkeypatch.setattr(sys, "argv", ["discover_todos.py"])

    assert discover_todos.main() == 0
    capsys.readouterr()
    assert selected_projects == [["music", "life", "quantum", "ai_manifest", "workspace"]]


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
    allowed_docs = capital_root / "docs"
    allowed_docs.mkdir()
    (allowed_docs / "parallel-test-execution.md").write_text(
        "benchmark reporting needs drift monitoring", encoding="utf-8"
    )
    (allowed_docs / "shared-structured-logging.md").write_text(
        "MCP observability alerts need operational controls", encoding="utf-8"
    )
    for relative_path in (
        "README.md",
        "AGENT_STARTUP.md",
        "COMPLIANCE.md",
        "PROJECT_NORTH_STAR.md",
        "docs/private.md",
        "data/holdings/private.md",
        "data/statements/private.md",
        "data/picks/private.md",
        "data/private.db",
        "features.env",
        ".env",
        "logs/private.md",
        "tmp/private.md",
    ):
        private_path = capital_root / relative_path
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_text("radio distribution details", encoding="utf-8")
    monkeypatch.setattr(
        discover_todos,
        "DISCOVERY_PROJECT_ROOTS",
        {**discover_todos.DISCOVERY_PROJECT_ROOTS, "capital": capital_root},
    )
    monkeypatch.setattr(sys, "argv", ["discover_todos.py", "--project", "capital"])

    assert discover_todos.main() == 0
    output = capsys.readouterr().out
    assert "benchmark observability dashboard" in output.lower()
    assert "public radio distribution" not in output.lower()
    assert "Dry-run only" in output


def test_capital_context_ignores_allowlisted_path_resolving_outside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    capital_root = tmp_path / "capital"
    docs_dir = capital_root / "docs"
    docs_dir.mkdir(parents=True)
    allowed_path = docs_dir / "parallel-test-execution.md"
    allowed_path.write_text("OUTSIDE_ROOT_CONTENT_MARKER", encoding="utf-8")
    outside_path = tmp_path / "private" / "account-details.md"
    outside_path.parent.mkdir()
    outside_path.write_text("PRIVATE_ACCOUNT_DATA_MARKER", encoding="utf-8")
    original_resolve = Path.resolve

    def resolve_with_escape(path: Path, strict: bool = False) -> Path:
        if path == allowed_path:
            return outside_path
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_escape)
    monkeypatch.setattr(
        discover_todos,
        "DISCOVERY_PROJECT_ROOTS",
        {**discover_todos.DISCOVERY_PROJECT_ROOTS, "capital": capital_root},
    )

    context = discover_todos._collect_context("capital")

    assert "OUTSIDE_ROOT_CONTENT_MARKER" not in context
    assert "PRIVATE_ACCOUNT_DATA_MARKER" not in context


def test_capital_candidates_preserve_deduplication_priority_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    candidate = {
        "project": "capital",
        "text": "Automate monitoring pipeline for documentation quality",
        "priority": 8,
        "rationale": "Reduce missed documentation regressions",
        "implementation_hints": "Run the existing test runner on a schedule",
        "context_snapshot": "The reviewed test policy documents the current workflow",
        "estimated_effort": "2 days",
        "dependencies": "Existing CI runner",
    }
    fallback_candidate = {
        "project": "capital",
        "text": "Design a manual quarterly operating review",
        "rationale": "Keep human review explicit",
        "implementation_hints": "Use an existing review checklist",
        "context_snapshot": "",
        "estimated_effort": "1 day",
        "dependencies": "",
    }
    candidates_file = tmp_path / "candidates.json"
    candidates_file.write_text(
        json.dumps([candidate, candidate, fallback_candidate]), encoding="utf-8"
    )
    monkeypatch.setattr(discover_todos, "init_db", lambda: None)
    monkeypatch.setattr(
        discover_todos,
        "get_open_todos",
        lambda: [{"project": "capital", "text": "Automate monitoring pipeline documentation"}],
    )
    fallback_calls: list[str] = []
    monkeypatch.setattr(
        discover_todos,
        "score_priority",
        lambda **kwargs: fallback_calls.append(kwargs["text"]) or 4,
    )
    inserted: list[dict[str, object]] = []
    monkeypatch.setattr(discover_todos, "add_todo", lambda **kwargs: inserted.append(kwargs))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "discover_todos.py",
            "--project",
            "capital",
            "--candidates-file",
            str(candidates_file),
            "--apply",
            "--yes",
        ],
    )

    assert discover_todos.main() == 0
    output = capsys.readouterr().out
    assert "SIMILAR" in output
    assert "Inserted todos (AI/TYLER auto-classified): 2" in output
    assert len(inserted) == 2
    assert fallback_calls == [fallback_candidate["text"]]
    assert inserted[0] == {
        "project": "capital",
        "text": candidate["text"],
        "priority": 8,
        "source": "AI",
        "autonomy_level": "full",
        "rationale": candidate["rationale"],
        "implementation_hints": candidate["implementation_hints"],
        "context_snapshot": candidate["context_snapshot"],
        "estimated_effort": candidate["estimated_effort"],
        "dependencies": candidate["dependencies"],
    }
    assert inserted[1]["priority"] == 4
    assert inserted[1]["source"] == "TYLER"
    assert inserted[1]["autonomy_level"] == "human"


def test_apply_inserts_only_explicitly_selected_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    candidates_file = tmp_path / "candidates.json"
    candidates_file.write_text(
        json.dumps(
            [
                {"project": "capital", "text": "Build an automated monitoring report", "priority": 7},
                {"project": "capital", "text": "Plan a manual review workshop", "priority": 5},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(discover_todos, "init_db", lambda: None)
    monkeypatch.setattr(discover_todos, "get_open_todos", lambda: [])
    inserted: list[str] = []
    monkeypatch.setattr(
        discover_todos,
        "add_todo",
        lambda **kwargs: inserted.append(kwargs["text"]),
    )
    answers = iter(("y", "2"))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(
        sys,
        "argv",
        ["discover_todos.py", "--project", "capital", "--candidates-file", str(candidates_file), "--apply"],
    )

    assert discover_todos.main() == 0
    output = capsys.readouterr().out
    assert inserted == ["Plan a manual review workshop"]
    assert "Inserted todos (AI/TYLER auto-classified): 1" in output


def test_yes_requires_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discover_todos = _load_discover_todos(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["discover_todos.py", "--project", "workspace", "--yes"],
    )

    with pytest.raises(SystemExit, match="2"):
        discover_todos.main()