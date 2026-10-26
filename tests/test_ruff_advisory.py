from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_runner() -> ModuleType:
    try:
        return importlib.import_module("tools.ruff_advisory")
    except ModuleNotFoundError as error:
        if error.name == "tools.ruff_advisory":
            pytest.fail("The Ruff advisory runner is not implemented")
        raise


def _fake_command_results() -> list[subprocess.CompletedProcess[str]]:
    path_sentinel = "private-path-sentinel.py"
    source_sentinel = "source-snippet-sentinel"
    token_sentinel = "credential-sentinel"
    remote_sentinel = "https://private.example.invalid/repository"
    commit = "a" * 40
    lint_json = json.dumps(
        [
            {
                "filename": path_sentinel,
                "message": source_sentinel,
                "code": "F401",
            }
        ]
    )
    format_diff = (
        f"Would reformat: {path_sentinel}\n"
        f"- {source_sentinel}\n"
        f"+ formatted-source-sentinel\n"
        "1 file would be reformatted\n"
    )
    return [
        subprocess.CompletedProcess([], 0, "ruff 0.17.2\n", ""),
        subprocess.CompletedProcess(
            [], 1, lint_json, f"token={token_sentinel} {remote_sentinel}\n"
        ),
        subprocess.CompletedProcess([], 1, format_diff, f"format-error={source_sentinel}\n"),
        subprocess.CompletedProcess([], 0, f"{commit}\n", ""),
    ]


def _set_up_runner_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root.mkdir()
    (root / "ruff.toml").write_text(
        'line-length = 100\ntarget-version = "py311"\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    results: list[subprocess.CompletedProcess[str] | OSError],
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        result = results.pop(0)
        if isinstance(result, OSError):
            raise result
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_ci_report_step_summary_and_logs_exclude_raw_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = tmp_path / "repo"
    _set_up_runner_root(repo_root, monkeypatch)
    summary_path = tmp_path / "step-summary.md"
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    _patch_subprocess(monkeypatch, _fake_command_results())

    runner = _load_runner()
    assert runner.main(["--ci"]) == 0

    artifact_dir = repo_root / "tmp" / "ruff-advisory-ci"
    artifact_files = list(artifact_dir.iterdir())
    assert [path.name for path in artifact_files] == ["summary.json"]
    report_text = artifact_files[0].read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert set(report) == {
        "repository",
        "commit",
        "ruff_version",
        "config_revision",
        "config_sha256",
        "scope",
        "elapsed_seconds",
        "finding_counts",
        "exit_codes",
        "error_categories",
    }
    assert report["repository"] == "owner/repository"
    assert report["ruff_version"] == "0.17.2"
    assert report["finding_counts"] == {"ruff_check": 1, "ruff_format_check": 1}
    assert report["exit_codes"] == {"ruff_check": 1, "ruff_format_check": 1}

    captured = capsys.readouterr()
    emitted_text = "\n".join(
        [report_text, summary_path.read_text(encoding="utf-8"), captured.out, captured.err]
    )
    for sentinel in (
        "private-path-sentinel.py",
        "source-snippet-sentinel",
        "credential-sentinel",
        "private.example.invalid",
        "formatted-source-sentinel",
    ):
        assert sentinel not in emitted_text
    assert not (repo_root / "tmp" / "ruff-advisory-local").exists()


def test_ci_report_replaces_raw_exception_text_with_generic_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = tmp_path / "repo"
    _set_up_runner_root(repo_root, monkeypatch)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    results = _fake_command_results()
    results[1] = OSError("token=exception-secret-sentinel at /private/source.py")
    _patch_subprocess(monkeypatch, results)

    runner = _load_runner()
    assert runner.main(["--ci"]) == 0

    artifact = repo_root / "tmp" / "ruff-advisory-ci" / "summary.json"
    report_text = artifact.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    emitted_text = report_text + captured.out + captured.err
    assert "exception-secret-sentinel" not in emitted_text
    assert "/private/source.py" not in emitted_text
    assert json.loads(report_text)["error_categories"]["ruff_check"] == "command_unavailable"
    assert not (repo_root / "tmp" / "ruff-advisory-local").exists()


def test_local_mode_keeps_full_diagnostics_under_ignored_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    _set_up_runner_root(repo_root, monkeypatch)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    results = _fake_command_results()
    results[0] = OSError("local-exception-sentinel at /private/runner")
    _patch_subprocess(monkeypatch, results)

    runner = _load_runner()
    assert runner.main([]) == 0

    diagnostics_dir = repo_root / "tmp" / "ruff-advisory-local"
    check_json = (diagnostics_dir / "ruff-check.json").read_text(encoding="utf-8")
    format_diff = (diagnostics_dir / "ruff-format.diff").read_text(encoding="utf-8")
    errors = (diagnostics_dir / "ruff-errors.log").read_text(encoding="utf-8")
    assert "private-path-sentinel.py" in check_json
    assert "source-snippet-sentinel" in check_json
    assert "source-snippet-sentinel" in format_diff
    assert "credential-sentinel" in errors
    assert "private.example.invalid" in errors
    assert "local-exception-sentinel" in errors


def test_ci_report_rejects_successful_unpinned_ruff_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = tmp_path / "repo"
    _set_up_runner_root(repo_root, monkeypatch)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    results = _fake_command_results()
    results[0] = subprocess.CompletedProcess([], 0, "ruff 0.17.3\n", "")
    _patch_subprocess(monkeypatch, results)

    runner = _load_runner()
    assert runner.main(["--ci"]) == 0

    report_text = (repo_root / "tmp" / "ruff-advisory-ci" / "summary.json").read_text(
        encoding="utf-8"
    )
    report = json.loads(report_text)
    assert report["ruff_version"] == "unavailable"
    assert report["error_categories"]["ruff_version"] == "invalid_output"
    assert "0.17.3" not in report_text + capsys.readouterr().out
