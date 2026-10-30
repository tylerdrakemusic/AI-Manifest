from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


FR_ID = "FR-20261025-gradual-mypy-adoption"
CONFIG_REVISION = "manifest-mypy-v1"
EXPECTED_MYPY_VERSION = "1.18.2"
_ERROR_RE = re.compile(r"(?m)^.+?:\d+(?::\d+)?: error: .+?(?: \[(?P<code>[a-z0-9-]+)\])?$")
_REPOSITORY_RE = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?(?:$|/)")
_REPOSITORY_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_VERSION_RE = re.compile(r"^mypy (?P<version>\d+(?:\.\d+){1,2})(?: \(compiled: (?:yes|no)\))?$")


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def run_command(command: Sequence[str]) -> dict[str, Any]:
    """Run a command and capture its exit status and output."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "returncode": None,
            "stdout": _text(getattr(error, "stdout", "")),
            "stderr": _text(getattr(error, "stderr", "")) or str(error),
        }
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _finding_counts(
    stdout: str, stderr: str, returncode: int | None
) -> tuple[int | None, dict[str, int]]:
    matches = list(_ERROR_RE.finditer(f"{stdout}\n{stderr}"))
    if returncode not in (0, 1) or (returncode == 1 and not matches):
        return None, {}
    counts = Counter(match.group("code") or "unknown" for match in matches)
    return len(matches), dict(sorted(counts.items()))


def _repository_slug(value: str | None) -> str | None:
    if not value:
        return None
    if _REPOSITORY_SLUG_RE.fullmatch(value):
        return value
    match = _REPOSITORY_RE.search(value.strip())
    if match and _REPOSITORY_SLUG_RE.fullmatch(match.group(1)):
        return match.group(1)
    return None


def _safe_commit(result: dict[str, Any]) -> str:
    commit = _text(result.get("stdout")).strip()
    if result.get("returncode") == 0 and re.fullmatch(r"[0-9a-f]{7,64}", commit):
        return commit
    return "unavailable"


def _error_category(result: dict[str, Any], valid: bool) -> str:
    if result.get("returncode") is None:
        return "command_unavailable"
    return "none" if valid else "invalid_output"


def _configured_paths(config_path: Path) -> tuple[list[str], str | None]:
    config = configparser.ConfigParser()
    try:
        loaded = config.read(config_path, encoding="utf-8")
    except (OSError, configparser.Error):
        return [], "configuration_unavailable"
    if not loaded or not config.has_section("mypy") or not config.has_option("mypy", "files"):
        return [], "configuration_unavailable"
    paths = [item.strip() for item in config.get("mypy", "files").split(",") if item.strip()]
    if not paths:
        return [], "configuration_unavailable"
    return paths, None


def _report(
    repo_root: Path,
    config_path: Path,
    paths: list[str],
    version_result: dict[str, Any],
    mypy_result: dict[str, Any],
    commit_result: dict[str, Any],
    remote_result: dict[str, Any],
    elapsed_seconds: float,
    config_error: str | None,
) -> dict[str, Any]:
    try:
        config_revision = hashlib.sha256(config_path.read_bytes()).hexdigest()
        config_category = config_error or "none"
    except OSError:
        config_revision = "unavailable"
        config_category = "configuration_unavailable"

    version = _text(version_result.get("stdout")).strip()
    version_match = _VERSION_RE.fullmatch(version)
    version_valid = version_result.get("returncode") == 0 and version_match is not None
    version_matches_expected = (
        version_valid
        and version_match is not None
        and version_match.group("version") == EXPECTED_MYPY_VERSION
    )
    if not version_valid:
        version = "unavailable"

    repository = _repository_slug(os.environ.get("GITHUB_REPOSITORY"))
    if repository is None and remote_result.get("returncode") == 0:
        repository = _repository_slug(_text(remote_result.get("stdout")).strip())
    finding_count, counts_by_code = _finding_counts(
        _text(mypy_result.get("stdout")),
        _text(mypy_result.get("stderr")),
        mypy_result.get("returncode"),
    )
    tool_error_categories = {
        "configuration": config_category,
        "version": (
            "expected_version_mismatch"
            if version_valid and not version_matches_expected
            else _error_category(version_result, version_valid)
        ),
        "mypy": _error_category(mypy_result, finding_count is not None),
        "commit": _error_category(commit_result, _safe_commit(commit_result) != "unavailable"),
        "repository": "none" if repository else "unavailable",
    }
    return {
        "fr_id": FR_ID,
        "repository": repository or "local",
        "commit": _safe_commit(commit_result),
        "mypy_version": version,
        "configuration_revision": config_revision,
        "config_revision": CONFIG_REVISION,
        "scan_scope": f"Configured Python paths: {', '.join(paths)}"
        if paths
        else "Configured Python paths: unavailable",
        "elapsed_seconds": elapsed_seconds,
        "finding_count": finding_count,
        "finding_counts_by_code": counts_by_code,
        "mypy_exit_code": mypy_result.get("returncode"),
        "tool_errors": {
            name: category != "none" for name, category in tool_error_categories.items()
        },
        "tool_error_categories": tool_error_categories,
    }


def _step_summary(report: dict[str, Any]) -> str:
    tool_error_categories = report["tool_error_categories"]
    error_summary = (
        ", ".join(
            f"{name}={category}"
            for name, category in tool_error_categories.items()
            if category != "none"
        )
        or "none"
    )
    return "\n".join(
        [
            "## Advisory mypy diagnostics",
            "",
            f"- Repository: `{report['repository']}`",
            f"- Commit: `{report['commit']}`",
            f"- mypy version: `{report['mypy_version']}`",
            f"- Configuration revision: `{report['configuration_revision']}`",
            f"- Scan scope: {_escape_markdown_text(str(report['scan_scope']))}",
            f"- Elapsed: {report['elapsed_seconds']:.3f} seconds",
            f"- Findings: `{report['finding_count']}`",
            f"- Tool errors: `{error_summary}`",
            "- Advisory only: mypy findings and tool failures do not gate CI.",
            "",
        ]
    )


def _escape_markdown_text(value: str) -> str:
    value = value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
    return re.sub(r"([`*_{}\[\]()#+\-.!|<>])", r"\\\1", value)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the configured mypy scope and record advisory diagnostics."""
    parser = argparse.ArgumentParser(description="Run advisory mypy checks.")
    parser.add_argument("--config", default="mypy.ini", help="mypy configuration path")
    parser.add_argument("--output-dir", help="directory beneath tmp/ for report output")
    parser.add_argument("--ci", action="store_true", help="write a sanitized CI summary only")
    args = parser.parse_args(argv)

    repo_root = Path.cwd()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_root / config_path
    paths, config_error = _configured_paths(config_path)
    started = time.perf_counter()
    version_result = run_command([sys.executable, "-m", "mypy", "--version"])
    commit_result = run_command(["git", "rev-parse", "HEAD"])
    remote_result = run_command(["git", "remote", "get-url", "origin"])
    mypy_result = run_command(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(config_path),
            "--no-incremental",
            "--follow-imports=skip",
        ]
    )
    elapsed_seconds = round(time.perf_counter() - started, 3)
    report = _report(
        repo_root,
        config_path,
        paths,
        version_result,
        mypy_result,
        commit_result,
        remote_result,
        elapsed_seconds,
        config_error,
    )

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("tmp") / ("mypy-advisory-ci" if args.ci else "mypy-advisory-local")
    )
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    if args.ci and not args.output_dir and os.environ.get("GITHUB_RUN_ID"):
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        output_dir = output_dir / f"{os.environ['GITHUB_RUN_ID']}-{attempt}"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if args.ci:
            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_path:
                with open(summary_path, "a", encoding="utf-8") as summary_file:
                    summary_file.write(_step_summary(report))
            print(_step_summary(report), end="")
        else:
            diagnostics = _text(mypy_result.get("stdout")) + _text(mypy_result.get("stderr"))
            (output_dir / "mypy-diagnostics.txt").write_text(diagnostics, encoding="utf-8")
            print(_step_summary(report), end="")
    except OSError:
        print("Advisory mypy report could not be written.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
