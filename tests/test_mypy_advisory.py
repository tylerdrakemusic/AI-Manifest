from __future__ import annotations

import configparser
import hashlib
import importlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

import pytest


def _load_runner() -> Any:
    try:
        return importlib.import_module("tools.mypy_advisory")
    except ModuleNotFoundError as error:
        if error.name == "tools.mypy_advisory":
            pytest.fail("The mypy advisory runner is not implemented")
        raise


def _set_up_project(root: Path) -> tuple[Path, Path, bytes, bytes]:
    config_path = root / "mypy.ini"
    config_path.write_text(
        "[mypy]\n"
        "python_version = 3.11\n"
        "follow_imports = skip\n"
        "no_incremental = True\n"
        "files = src/utils/audio_output_policy.py, src/utils/priority_scorer.py\n",
        encoding="utf-8",
    )
    source_paths = [
        root / "src" / "utils" / "audio_output_policy.py",
        root / "src" / "utils" / "priority_scorer.py",
    ]
    source_contents = [
        b"def resolve_name(value: str) -> str:\n    return value\n",
        b"def score(value: int) -> int:\n    return value\n",
    ]
    for path, content in zip(source_paths, source_contents, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return config_path, source_paths[0], source_contents[0], source_contents[1]


def _fake_mypy_results(
    diagnostic_output: str,
    *,
    mypy_version: str = "mypy 1.10.1 (compiled: yes)",
    remote_url: str = "https://github.com/tylerdrakemusic/AI-Manifest.git",
) -> tuple[list[list[str]], Any]:
    commit = "a" * 40
    commands: list[list[str]] = []

    def fake_run_command(command: Sequence[str]) -> dict[str, Any]:
        commands.append(list(command))
        if command[-1:] == ["--version"]:
            return {"returncode": 0, "stdout": f"{mypy_version}\n", "stderr": ""}
        if list(command) == ["git", "rev-parse", "HEAD"]:
            return {"returncode": 0, "stdout": f"{commit}\n", "stderr": ""}
        if list(command) == ["git", "remote", "get-url", "origin"]:
            return {"returncode": 0, "stdout": f"{remote_url}\n", "stderr": ""}
        if "-m" in command and "mypy" in command:
            return {"returncode": 1, "stdout": diagnostic_output, "stderr": ""}
        raise AssertionError(f"Unexpected command: {command}")

    return commands, fake_run_command


def test_ci_workflow_installs_exact_advisory_mypy_pin() -> None:
    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "test.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    installs = re.findall(
        r"(?m)^\s*if python -m pip install (mypy==[^\s]+) >/dev/null 2>&1; then$",
        workflow_text,
    )

    assert installs == ["mypy==1.18.2"]


def test_initial_mypy_configuration_limits_scan_to_selected_src_modules() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config = configparser.ConfigParser()
    config_path = project_root / "mypy.ini"

    assert config.read(config_path, encoding="utf-8"), "mypy.ini is missing"
    assert config["mypy"]["python_version"] == "3.11"
    assert config["mypy"]["follow_imports"] == "skip"
    assert config["mypy"].getboolean("no_incremental") is True
    assert [path.strip() for path in config["mypy"]["files"].split(",")] == [
        "src/utils/audio_output_policy.py",
        "src/utils/priority_scorer.py",
    ]


def test_runner_marks_valid_unexpected_mypy_version_as_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_project(tmp_path)
    output_dir = tmp_path / "tmp" / "mypy-advisory"
    commands, fake_run_command = _fake_mypy_results(
        "src/utils/audio_output_policy.py:1: error: Invalid return [return-value]\n",
        mypy_version="mypy 1.10.1 (compiled: yes)",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_load_runner(), "run_command", fake_run_command)

    result = _load_runner().main(["--config", "mypy.ini", "--output-dir", str(output_dir)])

    report = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert result == 0
    assert report["mypy_version"] == "mypy 1.10.1 (compiled: yes)"
    assert report["tool_errors"]["version"] is True
    assert report["tool_error_categories"]["version"] == "expected_version_mismatch"
    assert all(type(error) is bool for error in report["tool_errors"].values())
    assert commands


def test_runner_accepts_pinned_mypy_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_up_project(tmp_path)
    output_dir = tmp_path / "tmp" / "mypy-advisory"
    _, fake_run_command = _fake_mypy_results(
        "src/utils/audio_output_policy.py:1: error: Invalid return [return-value]\n",
        mypy_version="mypy 1.18.2 (compiled: yes)",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_load_runner(), "run_command", fake_run_command)

    result = _load_runner().main(["--config", "mypy.ini", "--output-dir", str(output_dir)])

    report = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert result == 0
    assert report["mypy_version"] == "mypy 1.18.2 (compiled: yes)"
    assert report["tool_errors"]["version"] is False
    assert report["tool_error_categories"]["version"] == "none"
    assert all(type(error) is bool for error in report["tool_errors"].values())


def test_runner_reports_findings_and_metadata_without_gating_or_editing_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path, source_path, source_bytes, second_source_bytes = _set_up_project(tmp_path)
    second_source_path = tmp_path / "src" / "utils" / "priority_scorer.py"
    output_dir = tmp_path / "tmp" / "mypy-advisory"
    diagnostics = (
        "src/utils/audio_output_policy.py:1: error: Invalid return [return-value]\n"
        "src/utils/priority_scorer.py:1: error: Invalid argument [arg-type]\n"
    )
    commands, fake_run_command = _fake_mypy_results(diagnostics)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_load_runner(), "run_command", fake_run_command)

    result = _load_runner().main(["--config", "mypy.ini", "--output-dir", str(output_dir)])

    report = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    mypy_command = next(
        command
        for command in commands
        if "-m" in command and "mypy" in command and command[-1:] != ["--version"]
    )
    assert result == 0
    assert report["repository"] == "tylerdrakemusic/AI-Manifest"
    assert report["commit"] == "a" * 40
    assert report["mypy_version"] == "mypy 1.10.1 (compiled: yes)"
    assert report["configuration_revision"] == hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert (
        report["scan_scope"]
        == "Configured Python paths: src/utils/audio_output_policy.py, src/utils/priority_scorer.py"
    )
    assert isinstance(report["elapsed_seconds"], float)
    assert report["finding_count"] == 2
    assert report["finding_counts_by_code"] == {"arg-type": 1, "return-value": 1}
    assert "--no-incremental" in mypy_command
    assert source_path.read_bytes() == source_bytes
    assert second_source_path.read_bytes() == second_source_bytes
    assert diagnostics in (output_dir / "mypy-diagnostics.txt").read_text(encoding="utf-8")


def test_ci_summary_excludes_raw_diagnostics_and_remote_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_up_project(tmp_path)
    output_dir = tmp_path / "tmp" / "mypy-advisory-ci"
    summary_path = tmp_path / "step-summary.md"
    diagnostic_secret = "DIAGNOSTIC_SECRET_SENTINEL"
    remote_secret = "REMOTE_SECRET_SENTINEL"
    remote_url = f"https://token:{remote_secret}@github.com/tylerdrakemusic/AI-Manifest.git"
    commands, fake_run_command = _fake_mypy_results(
        f"src/utils/audio_output_policy.py:1: error: {diagnostic_secret} [assignment]\n",
        remote_url=remote_url,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setattr(_load_runner(), "run_command", fake_run_command)

    result = _load_runner().main(["--ci", "--config", "mypy.ini", "--output-dir", str(output_dir)])

    report_text = (output_dir / "summary.json").read_text(encoding="utf-8")
    summary_text = summary_path.read_text(encoding="utf-8")
    emitted_text = report_text + summary_text + capsys.readouterr().out
    assert result == 0
    assert json.loads(report_text)["repository"] == "tylerdrakemusic/AI-Manifest"
    assert json.loads(report_text)["finding_count"] == 1
    for secret in (remote_secret, diagnostic_secret, remote_url):
        assert secret not in emitted_text
    assert not (output_dir / "mypy-diagnostics.txt").exists()


def test_ci_summary_surfaces_version_mismatch_without_raw_diagnostics_or_gating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_up_project(tmp_path)
    output_dir = tmp_path / "tmp" / "mypy-advisory-ci"
    summary_path = tmp_path / "step-summary.md"
    diagnostic_secret = "RAW_DIAGNOSTIC_SENTINEL"
    _, fake_run_command = _fake_mypy_results(
        f"src/utils/audio_output_policy.py:1: error: {diagnostic_secret} [assignment]\n",
        mypy_version="mypy 1.10.1 (compiled: yes)",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setattr(_load_runner(), "run_command", fake_run_command)

    result = _load_runner().main(["--ci", "--config", "mypy.ini", "--output-dir", str(output_dir)])

    report_text = (output_dir / "summary.json").read_text(encoding="utf-8")
    summary_text = summary_path.read_text(encoding="utf-8")
    emitted_text = report_text + summary_text + capsys.readouterr().out
    report = json.loads(report_text)
    assert result == 0
    assert report["mypy_version"] == "mypy 1.10.1 (compiled: yes)"
    assert report["tool_errors"]["version"] is True
    assert report["tool_error_categories"]["version"] == "expected_version_mismatch"
    assert "version=expected_version_mismatch" in summary_text
    assert diagnostic_secret not in summary_text
    assert diagnostic_secret not in emitted_text
    assert not (output_dir / "mypy-diagnostics.txt").exists()


def test_step_summary_escapes_untrusted_scope_markdown() -> None:
    report = {
        "fr_id": "FR-20261025-gradual-mypy-adoption",
        "repository": "owner/repo",
        "commit": "a" * 40,
        "mypy_version": "mypy 1.18.2",
        "configuration_revision": "a" * 64,
        "config_revision": "manifest-mypy-v1",
        "scan_scope": (
            "Configured Python paths: src/utils/a.py\n- [forged](https://example.test) "
            "<https://autolink.example>"
        ),
        "elapsed_seconds": 0.1,
        "finding_count": 0,
        "finding_counts_by_code": {},
        "mypy_exit_code": 0,
        "tool_errors": {},
        "tool_error_categories": {"version": "none"},
    }

    summary = _load_runner()._step_summary(report)

    assert r"\n\- \[forged\]\(https://example\.test\)" in summary
    assert r"\<https://autolink\.example\>" in summary
    assert "\n- [forged]" not in summary
