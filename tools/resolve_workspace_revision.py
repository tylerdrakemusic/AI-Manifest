from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


PEER_REPOSITORY = "tylerdrakemusic/-Workspace"
DEFAULT_REF = "main"
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


def _lookup_revision(remote: str, ref: str) -> str | None:
    remote_ref = f"refs/heads/{ref}"
    command = ["git", "ls-remote", "--exit-code", "--heads", remote, remote_ref]
    last_error = "unknown git error"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = _run(command)
        except OSError as error:
            last_error = str(error)
        else:
            if result.returncode == 2:
                return None
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if len(fields) == 2 and fields[1] == remote_ref:
                        return fields[0]
                return None
            last_error = result.stderr.strip() or f"git exited with {result.returncode}"

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"Workspace ref lookup for {remote_ref} failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def _run_required(command: list[str], operation: str) -> None:
    try:
        result = _run(command)
    except OSError as error:
        raise RuntimeError(f"Workspace {operation} failed: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"git exited with {result.returncode}"
        raise RuntimeError(f"Workspace {operation} failed: {detail}")


def _checkout_revision(workspace_path: Path, remote: str, revision: str) -> str:
    workspace_path.mkdir(parents=True, exist_ok=True)
    _run_required(["git", "-C", str(workspace_path), "init"], "repository initialization")
    _run_required(
        ["git", "-C", str(workspace_path), "remote", "add", "origin", remote],
        "remote configuration",
    )

    last_error = "unknown git error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            fetch = _run(
                [
                    "git",
                    "-C",
                    str(workspace_path),
                    "fetch",
                    "--no-tags",
                    "--depth=1",
                    "origin",
                    revision,
                ]
            )
            if fetch.returncode != 0:
                last_error = fetch.stderr.strip() or f"git fetch exited with {fetch.returncode}"
            else:
                checkout = _run(
                    ["git", "-C", str(workspace_path), "checkout", "--detach", revision]
                )
                if checkout.returncode != 0:
                    last_error = checkout.stderr.strip() or (
                        f"git checkout exited with {checkout.returncode}"
                    )
                else:
                    verification = _run(
                        ["git", "-C", str(workspace_path), "rev-parse", "HEAD"]
                    )
                    if verification.returncode != 0:
                        last_error = verification.stderr.strip() or (
                            f"git rev-parse exited with {verification.returncode}"
                        )
                    else:
                        checked_out_revision = verification.stdout.strip()
                        if checked_out_revision == revision:
                            return checked_out_revision
                        last_error = (
                            f"checked-out SHA mismatch: expected {revision}, "
                            f"got {checked_out_revision}"
                        )
        except OSError as error:
            last_error = str(error)

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"Workspace checkout failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def main() -> int:
    """Resolve, check out, and report the peer Workspace revision."""
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    remote = f"https://github.com/{PEER_REPOSITORY}.git"
    selected_ref = DEFAULT_REF
    fallback = "none"

    if event_name == "pull_request":
        head_ref = os.environ.get("GITHUB_HEAD_REF", "")
        if not head_ref:
            raise RuntimeError("GITHUB_HEAD_REF is empty for a pull request")
        revision = _lookup_revision(remote, head_ref)
        if revision is None:
            fallback = f"main (PR ref {head_ref} not found)"
            revision = _lookup_revision(remote, DEFAULT_REF)
            if revision is None:
                raise RuntimeError("Workspace default ref main was not found")
        else:
            selected_ref = head_ref
    else:
        revision = _lookup_revision(remote, DEFAULT_REF)
        if revision is None:
            raise RuntimeError("Workspace default ref main was not found")

    workspace_path = Path(os.environ["GITHUB_WORKSPACE"]) / "workspace"
    checked_out_revision = _checkout_revision(workspace_path, remote, revision)
    summary_path = Path(os.environ["GITHUB_STEP_SUMMARY"])
    summary = (
        "## Paired Workspace revision\n"
        f"- Peer repository: {PEER_REPOSITORY}\n"
        f"- Selected ref: {selected_ref}\n"
        f"- Fallback: {fallback}\n"
        f"- Checked-out SHA: {checked_out_revision}\n"
    )
    with summary_path.open("a", encoding="utf-8") as summary_file:
        summary_file.write(summary)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"Paired Workspace revision setup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error