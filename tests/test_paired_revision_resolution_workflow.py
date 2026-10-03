from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETUP_SCRIPT = PROJECT_ROOT / "tools" / "resolve_workspace_revision.py"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "test.yml"
PEER_REPOSITORY = "tylerdrakemusic/-Workspace"
PEER_SHA = "a" * 40


@pytest.fixture
def setup_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("resolve_workspace_revision", SETUP_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module: ModuleType,
    *,
    event_name: str,
    head_ref: str | None,
    responses: dict[str, list[tuple[int, str, str]]],
) -> tuple[list[tuple[str, ...]], list[float], Path]:
    workspace = tmp_path / "checkout"
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    if head_ref is not None:
        monkeypatch.setenv("GITHUB_HEAD_REF", head_ref)
    else:
        monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)

    calls: list[tuple[str, ...]] = []
    sleeps: list[float] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        call = tuple(command)
        calls.append(call)
        if "ls-remote" in call:
            key = f"lookup:{call[-1]}"
        elif "fetch" in call:
            key = "fetch"
        elif "checkout" in call:
            key = "checkout"
        elif "rev-parse" in call:
            key = "rev-parse"
        else:
            key = "success"

        result = responses.get(key, [(0, "", "")]).pop(0)
        return subprocess.CompletedProcess(
            args=command,
            returncode=result[0],
            stdout=result[1],
            stderr=result[2],
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    return calls, sleeps, summary_path


def _found_ref(branch: str) -> tuple[int, str, str]:
    return 0, f"{PEER_SHA}\trefs/heads/{branch}\n", ""


def test_pr_checks_out_peer_branch_sha_and_records_checkout_summary(
    setup_script_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    branch = "feature/paired-change"
    calls, _, summary_path = _configure_setup(
        monkeypatch,
        tmp_path,
        setup_script_module,
        event_name="pull_request",
        head_ref=branch,
        responses={
            f"lookup:refs/heads/{branch}": [_found_ref(branch)],
            "rev-parse": [(0, f"{PEER_SHA}\n", "")],
        },
    )

    assert setup_script_module.main() == 0
    assert (
        "git",
        "ls-remote",
        "--exit-code",
        "--heads",
        f"https://github.com/{PEER_REPOSITORY}.git",
        f"refs/heads/{branch}",
    ) in calls
    assert (
        "git",
        "-C",
        str(tmp_path / "checkout" / "workspace"),
        "fetch",
        "--no-tags",
        "--depth=1",
        "origin",
        PEER_SHA,
    ) in calls
    assert (
        "git",
        "-C",
        str(tmp_path / "checkout" / "workspace"),
        "checkout",
        "--detach",
        PEER_SHA,
    ) in calls
    summary = summary_path.read_text(encoding="utf-8")
    assert PEER_REPOSITORY in summary
    assert f"Selected ref: {branch}" in summary
    assert f"Checked-out SHA: {PEER_SHA}" in summary


def test_pr_falls_back_only_after_peer_branch_is_confirmed_absent(
    setup_script_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    branch = "feature/no-peer"
    _, _, summary_path = _configure_setup(
        monkeypatch,
        tmp_path,
        setup_script_module,
        event_name="pull_request",
        head_ref=branch,
        responses={
            f"lookup:refs/heads/{branch}": [(2, "", "")],
            "lookup:refs/heads/main": [_found_ref("main")],
            "rev-parse": [(0, f"{PEER_SHA}\n", "")],
        },
    )

    assert setup_script_module.main() == 0
    summary = summary_path.read_text(encoding="utf-8")
    assert "Selected ref: main" in summary
    assert f"Fallback: main (PR ref {branch} not found)" in summary


def test_push_uses_workspace_default_branch(
    setup_script_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls, _, summary_path = _configure_setup(
        monkeypatch,
        tmp_path,
        setup_script_module,
        event_name="push",
        head_ref=None,
        responses={
            "lookup:refs/heads/main": [_found_ref("main")],
            "rev-parse": [(0, f"{PEER_SHA}\n", "")],
        },
    )

    assert setup_script_module.main() == 0
    assert any(call[-1] == "refs/heads/main" for call in calls if "ls-remote" in call)
    assert "Selected ref: main" in summary_path.read_text(encoding="utf-8")


def test_transient_lookup_and_checkout_failures_retry_and_then_succeed(
    setup_script_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    branch = "feature/retry"
    calls, sleeps, _ = _configure_setup(
        monkeypatch,
        tmp_path,
        setup_script_module,
        event_name="pull_request",
        head_ref=branch,
        responses={
            f"lookup:refs/heads/{branch}": [
                (128, "", "temporary network error"),
                _found_ref(branch),
            ],
            "fetch": [
                (128, "", "temporary fetch error"),
                (0, "", ""),
                (0, "", ""),
            ],
            "checkout": [(128, "", "temporary checkout error"), (0, "", "")],
            "rev-parse": [(0, f"{PEER_SHA}\n", "")],
        },
    )

    assert setup_script_module.main() == 0
    assert sum("ls-remote" in call for call in calls) == 2
    assert sum("fetch" in call for call in calls) == 3
    assert sum("checkout" in call for call in calls) == 2
    assert sleeps == [1, 1, 1]


def test_exhausted_lookup_fails_without_fallback_or_checkout(
    setup_script_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    branch = "feature/lookup-down"
    calls, sleeps, summary_path = _configure_setup(
        monkeypatch,
        tmp_path,
        setup_script_module,
        event_name="pull_request",
        head_ref=branch,
        responses={
            f"lookup:refs/heads/{branch}": [(128, "", "network unavailable")] * 3,
        },
    )

    with pytest.raises(RuntimeError, match="lookup.*3 attempts"):
        setup_script_module.main()

    assert sum("ls-remote" in call for call in calls) == 3
    assert sum("refs/heads/main" in call for call in calls) == 0
    assert sum("fetch" in call for call in calls) == 0
    assert sleeps == [1, 1]
    assert not summary_path.exists()


def test_exhausted_checkout_fails_after_three_attempts_without_summary(
    setup_script_module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    branch = "feature/checkout-down"
    calls, sleeps, summary_path = _configure_setup(
        monkeypatch,
        tmp_path,
        setup_script_module,
        event_name="pull_request",
        head_ref=branch,
        responses={
            f"lookup:refs/heads/{branch}": [_found_ref(branch)],
            "checkout": [(128, "", "checkout unavailable")] * 3,
        },
    )

    with pytest.raises(RuntimeError, match="checkout.*3 attempts"):
        setup_script_module.main()

    assert sum("checkout" in call for call in calls) == 3
    assert sum("fetch" in call for call in calls) == 3
    assert sleeps == [1, 1]
    assert not summary_path.exists()


def test_paired_revision_setup_stays_before_the_existing_test_lane() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    setup_position = workflow.find("name: Set up paired Workspace revision")
    tests_position = workflow.find("name: Run tests in parallel")
    assert setup_position >= 0, "paired Workspace setup step is missing"
    assert tests_position >= 0, "existing parallel test step is missing"
    assert setup_position < tests_position
    assert "python tools/resolve_workspace_revision.py" in workflow
    assert 'pytest --collect-only -q -o addopts= -m "not playwright and not live"' in workflow
    assert "python tools/run_tests.py --parallel --junitxml=tmp/pytest-junit.xml" in workflow


def test_checkout_uses_read_only_permissions_without_persisting_credentials() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "    permissions:\n      contents: read\n" in workflow
    assert (
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          persist-credentials: false\n"
    ) in workflow