from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


CONFIG_REVISION = "manifest-ruff-v1"
SCOPE = "Python files selected by Ruff in repository scope; non-Python files are not scanned."
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RUFF_VERSION_PATTERN = re.compile(r"^ruff ([0-9]+(?:\.[0-9]+){1,2})$")
_PINNED_RUFF_VERSION = "0.17.2"
_FORMAT_COUNT_PATTERN = re.compile(r"(?m)^(\d+) files? would be reformatted\b")


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: str
    stderr: str
    error: str | None = None


def _run(command: Sequence[str], cwd: Path) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return CommandResult(None, "", "", str(error))
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _lint_count(result: CommandResult) -> int | None:
    try:
        findings = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return len(findings) if isinstance(findings, list) else None


def _format_count(result: CommandResult) -> int | None:
    if result.returncode == 0:
        return 0
    output = f"{result.stdout}\n{result.stderr}"
    match = _FORMAT_COUNT_PATTERN.search(output)
    return int(match.group(1)) if match else None


def _category(result: CommandResult, output_valid: bool) -> str:
    if result.error is not None:
        return "command_unavailable"
    if result.returncode is None:
        return "command_unavailable"
    if not output_valid:
        return "invalid_output"
    return "none"


def _safe_repository_name(value: str | None) -> str:
    if value and _REPOSITORY_PATTERN.fullmatch(value):
        return value
    return "unavailable"


def _safe_commit(result: CommandResult) -> str:
    commit = result.stdout.strip()
    if result.returncode == 0 and _COMMIT_PATTERN.fullmatch(commit):
        return commit
    return "unavailable"


def _safe_ruff_version(result: CommandResult) -> str:
    match = _RUFF_VERSION_PATTERN.fullmatch(result.stdout.strip())
    if result.returncode == 0 and match and match.group(1) == _PINNED_RUFF_VERSION:
        return match.group(1)
    return "unavailable"


def _write_local_diagnostics(
    repo_root: Path,
    check_result: CommandResult,
    format_result: CommandResult,
    version_result: CommandResult,
    commit_result: CommandResult,
) -> None:
    diagnostics_dir = repo_root / "tmp" / "ruff-advisory-local"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "ruff-check.json").write_text(check_result.stdout, encoding="utf-8")
    (diagnostics_dir / "ruff-format.diff").write_text(
        f"{format_result.stdout}{format_result.stderr}", encoding="utf-8"
    )
    error_sections: list[str] = []
    for name, result in (
        ("ruff_version", version_result),
        ("ruff_check", check_result),
        ("ruff_format_check", format_result),
        ("git_commit", commit_result),
    ):
        details = "\n".join(part for part in (result.stderr, result.error) if part)
        if details:
            error_sections.append(f"[{name}]\n{details}")
    (diagnostics_dir / "ruff-errors.log").write_text("\n\n".join(error_sections), encoding="utf-8")


def _make_summary(
    repo_root: Path,
    version_result: CommandResult,
    check_result: CommandResult,
    format_result: CommandResult,
    commit_result: CommandResult,
    elapsed_seconds: float,
) -> dict[str, object]:
    check_count = _lint_count(check_result)
    format_count = _format_count(format_result)
    config_path = repo_root / "ruff.toml"
    try:
        config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
        config_category = "none"
    except OSError:
        config_hash = "unavailable"
        config_category = "configuration_unavailable"

    version = _safe_ruff_version(version_result)
    commit = _safe_commit(commit_result)
    check_category = _category(check_result, check_count is not None)
    format_category = _category(format_result, format_count is not None)
    version_category = _category(version_result, version != "unavailable")
    commit_category = _category(commit_result, commit != "unavailable")
    repository = _safe_repository_name(os.environ.get("GITHUB_REPOSITORY"))

    return {
        "repository": repository,
        "commit": commit,
        "ruff_version": version,
        "config_revision": CONFIG_REVISION,
        "config_sha256": config_hash,
        "scope": SCOPE,
        "elapsed_seconds": elapsed_seconds,
        "finding_counts": {
            "ruff_check": check_count,
            "ruff_format_check": format_count,
        },
        "exit_codes": {
            "ruff_check": check_result.returncode,
            "ruff_format_check": format_result.returncode,
        },
        "error_categories": {
            "configuration": config_category,
            "ruff_version": version_category,
            "ruff_check": check_category,
            "ruff_format_check": format_category,
            "commit": commit_category,
        },
    }


def _format_step_summary(report: dict[str, object]) -> str:
    counts = report["finding_counts"]
    exit_codes = report["exit_codes"]
    categories = report["error_categories"]
    assert isinstance(counts, dict)
    assert isinstance(exit_codes, dict)
    assert isinstance(categories, dict)
    return "\n".join(
        [
            "## Advisory Ruff diagnostics",
            "",
            f"- Repository: `{report['repository']}`",
            f"- Commit: `{report['commit']}`",
            f"- Ruff version: `{report['ruff_version']}`",
            f"- Config revision: `{report['config_revision']}`",
            f"- Config SHA-256: `{report['config_sha256']}`",
            f"- Scope: {report['scope']}",
            f"- Elapsed: {report['elapsed_seconds']:.3f} seconds",
            f"- Findings: lint `{counts['ruff_check']}`, format `{counts['ruff_format_check']}`",
            f"- Exit codes: lint `{exit_codes['ruff_check']}`, format `{exit_codes['ruff_format_check']}`",
            f"- Generic error categories: `{json.dumps(categories, sort_keys=True)}`",
            "- Advisory only: Ruff findings and tool failures do not gate CI.",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run advisory Ruff checks.")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Write only a sanitized aggregate summary for CI artifact upload.",
    )
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    ruff_command = [sys.executable, "-m", "ruff"]
    version_result = _run([*ruff_command, "--version"], repo_root)
    started = time.perf_counter()
    check_result = _run([*ruff_command, "check", "--output-format=json", "."], repo_root)
    format_result = _run([*ruff_command, "format", "--check", "--diff", "."], repo_root)
    elapsed_seconds = round(time.perf_counter() - started, 3)
    commit_result = _run(["git", "rev-parse", "HEAD"], repo_root)
    report = _make_summary(
        repo_root,
        version_result,
        check_result,
        format_result,
        commit_result,
        elapsed_seconds,
    )

    if args.ci:
        artifact_dir = repo_root / "tmp" / "ruff-advisory-ci"
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "summary.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary = _format_step_summary(report)
            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_path:
                with open(summary_path, "a", encoding="utf-8") as summary_file:
                    summary_file.write(summary)
            print(summary, end="")
        except OSError:
            print("Advisory Ruff summary could not be written.", file=sys.stderr)
        return 0

    _write_local_diagnostics(
        repo_root,
        check_result,
        format_result,
        version_result,
        commit_result,
    )
    print(_format_step_summary(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
