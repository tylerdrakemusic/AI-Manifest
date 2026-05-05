"""Bulk re-score open todos in manifest_todos.db.

Usage examples:
    C:\\G\\python.exe tools/bulk_score_todos.py
    C:\\G\\python.exe tools/bulk_score_todos.py --apply
    C:\\G\\python.exe tools/bulk_score_todos.py --apply --yes --project music --limit 25
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.ollama import OllamaClient
from src.utils.priority_scorer import score_priority
from src.utils.todos_db import get_open_todos, update_priority


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bulk re-score open todos with preview and explicit apply confirmation."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write new priorities to DB. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation prompt in --apply mode.",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Optional project filter (default: all projects).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of open todos to process.",
    )
    return parser


def _excerpt(text: str, max_len: int = 72) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def _print_preview(items: list[dict[str, Any]]) -> None:
    print("\nPreview of proposed priority changes")
    print("ID    PROJECT      OLD -> NEW  TEXT")
    print("-" * 90)
    for row in items:
        print(
            f"{row['id']:<5} {row['project']:<12} {row['old_priority']:>2} -> {row['new_priority']:<2}  "
            f"{_excerpt(row['text'])}"
        )
    if not items:
        print("(no successfully rescored rows to preview)")


def _priority_bucket(p: int) -> str:
    """Map a priority 1-10 to a human-readable bucket label."""
    if p >= 9:
        return "critical (9-10)"
    if p >= 7:
        return "high (7-8)"
    if p >= 4:
        return "medium (4-6)"
    return "low (1-3)"


def _distribution(items: list[int]) -> dict[str, int]:
    """Count items by priority bucket."""
    buckets: dict[str, int] = {
        "critical (9-10)": 0,
        "high (7-8)": 0,
        "medium (4-6)": 0,
        "low (1-3)": 0,
    }
    for p in items:
        buckets[_priority_bucket(p)] += 1
    return buckets


def _print_distribution_report(preview_rows: list[dict[str, Any]]) -> None:
    """Print before/after priority distribution for scored rows."""
    if not preview_rows:
        return
    before = _distribution([r["old_priority"] for r in preview_rows])
    after = _distribution([r["new_priority"] for r in preview_rows])
    print("\nProposed priority distribution")
    print(f"  {'Bucket':<20} {'Before':>6}  {'After':>5}")
    print("  " + "-" * 34)
    for bucket in ("critical (9-10)", "high (7-8)", "medium (4-6)", "low (1-3)"):
        print(f"  {bucket:<20} {before[bucket]:>6}  {after[bucket]:>5}")


def _print_summary(stats: dict[str, int], apply_mode: bool) -> None:
    mode = "APPLY" if apply_mode else "DRY-RUN"
    print(f"\nSummary ({mode})")
    print(f"  scanned:   {stats['scanned']}")
    print(f"  rescored:  {stats['rescored']}")
    print(f"  updated:   {stats['updated']}")
    print(f"  unchanged: {stats['unchanged']}")
    print(f"  failed:    {stats['failed']}")
    print(f"  skipped:   {stats['skipped']}")


def _coerce_limit(raw_limit: int | None) -> int | None:
    if raw_limit is None:
        return None
    if raw_limit <= 0:
        raise ValueError(f"--limit must be > 0, got {raw_limit}")
    return raw_limit


def _detect_backends() -> tuple[bool, bool]:
    has_openai = bool(os.environ.get("OPENAPI_TOKEN")) and (
        importlib.util.find_spec("openai") is not None
    )
    has_ollama = OllamaClient().health_check()
    return has_ollama, has_openai


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        limit = _coerce_limit(args.limit)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    rows = get_open_todos(args.project)
    if limit is not None:
        rows = rows[:limit]

    has_ollama, has_openai = _detect_backends()
    print(
        "Scoring backends: "
        f"Ollama={'up' if has_ollama else 'down'}, "
        f"OpenAI={'configured' if has_openai else 'not-configured'}"
    )

    stats: dict[str, int] = {
        "scanned": len(rows),
        "rescored": 0,
        "updated": 0,
        "unchanged": 0,
        "failed": 0,
        "skipped": 0,
    }

    context_by_project: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        project = str(row.get("project", "")).strip()
        if project and project not in context_by_project:
            context_by_project[project] = get_open_todos(project)

    preview_rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for row in rows:
        try:
            todo_id = int(row["id"])
            project = str(row["project"])
            text = str(row["text"])
            old_priority = int(row.get("priority", 5))
            existing = context_by_project.get(project, [])
            if not has_ollama and not has_openai:
                raise RuntimeError("no scoring backend available (Ollama down, OpenAI unavailable)")
            new_priority = score_priority(text, project, existing_todos=existing)
            if new_priority not in range(1, 11):
                raise ValueError(f"score out of range: {new_priority}")
        except Exception as exc:
            stats["failed"] += 1
            stats["skipped"] += 1
            failures.append(f"id={row.get('id', '?')} project={row.get('project', '?')}: {exc}")
            continue

        changed = new_priority != old_priority
        if changed:
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1
        stats["rescored"] += 1

        preview_rows.append(
            {
                "id": todo_id,
                "project": project,
                "text": text,
                "old_priority": old_priority,
                "new_priority": new_priority,
                "changed": changed,
            }
        )

    _print_preview(preview_rows)
    _print_distribution_report(preview_rows)

    if failures:
        print("\nFailures")
        for item in failures[:20]:
            print(f"  - {item}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

    if not args.apply:
        stats["skipped"] += stats["updated"]
        _print_summary(stats, apply_mode=False)
        return 0

    if stats["updated"] == 0:
        _print_summary(stats, apply_mode=True)
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            print("\nApply mode requires confirmation; re-run with --yes for non-interactive use.")
            stats["skipped"] += stats["updated"]
            _print_summary(stats, apply_mode=True)
            return 2
        answer = input(
            f"\nAbout to update {stats['updated']} row(s). Type APPLY to continue: "
        ).strip()
        if answer != "APPLY":
            print("Canceled: no changes written.")
            stats["skipped"] += stats["updated"]
            _print_summary(stats, apply_mode=True)
            return 0

    pending_updates = [row for row in preview_rows if row["changed"]]
    stats["updated"] = 0

    for row in pending_updates:
        try:
            ok = update_priority(int(row["id"]), int(row["new_priority"]))
            if ok:
                stats["updated"] += 1
            else:
                stats["failed"] += 1
                failures.append(
                    f"id={row['id']} project={row['project']}: update returned no row"
                )
        except Exception as exc:
            stats["failed"] += 1
            failures.append(f"id={row['id']} project={row['project']}: update failed: {exc}")

    if failures:
        print("\nPost-apply failures")
        for item in failures[:20]:
            print(f"  - {item}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

    _print_summary(stats, apply_mode=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
