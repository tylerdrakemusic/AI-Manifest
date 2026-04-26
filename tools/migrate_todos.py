"""Migrate flat TODO_AI.md / TODO_TYLER.md files to the todos DB.

Idempotent — re-running will not duplicate rows (unique index on
project+source+text).  After a clean migration the flat files are
removed from disk.

Usage
-----
    python tools/migrate_todos.py            # migrate + delete flat files
    python tools/migrate_todos.py --dry-run  # preview only, no writes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.todos_db import init_db, insert_todo

WORKSPACE_ROOT = Path(r"f:\\")

# All project TODO sources in discovery order
TODO_SOURCES = [
    {"key": "music",       "root": WORKSPACE_ROOT / "❤Music"},
    {"key": "life",        "root": WORKSPACE_ROOT / "∞Life"},
    {"key": "quantum",     "root": WORKSPACE_ROOT / "⟨ψ⟩Quantum"},
    {"key": "ai_manifest", "root": WORKSPACE_ROOT / "👁AI-Manifest"},
    {"key": "workspace",   "root": WORKSPACE_ROOT / "⊕Workspace"},
]


def _extract_unchecked(text: str) -> list[str]:
    """Extract unchecked `- [ ]` items from markdown."""
    items: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- [ ]"):
            items.append(s[5:].strip())
    return items


def _all_todo_paths() -> list[Path]:
    return [
        src["root"] / fname
        for src in TODO_SOURCES
        for fname in ("TODO_AI.md", "TODO_TYLER.md")
    ]


def migrate(dry_run: bool = False) -> dict[str, int]:
    """Migrate flat files to DB. Returns counts dict."""
    if not dry_run:
        init_db()

    inserted = 0
    skipped = 0
    files_removed = 0

    for src in TODO_SOURCES:
        root = src["root"]
        project = src["key"]

        for filename, source_label in [("TODO_AI.md", "AI"), ("TODO_TYLER.md", "TYLER")]:
            path = root / filename
            if not path.exists():
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  WARN: could not read {path}: {e}", file=sys.stderr)
                continue

            items = _extract_unchecked(text)
            if dry_run:
                for item in items:
                    print(f"  [DRY] {project}/{source_label}: {item[:100]}")
                inserted += len(items)
                continue

            for item in items:
                row_id = insert_todo(project, source_label, item)
                if row_id is not None:
                    inserted += 1
                else:
                    skipped += 1

    print(f"Migration: {inserted} inserted, {skipped} skipped (duplicates)")

    if not dry_run:
        print("Removing flat TODO files...")
        for path in _all_todo_paths():
            if not path.exists():
                continue
            try:
                path.unlink()
                print(f"  REMOVED: {path}")
                files_removed += 1
            except Exception as e:
                print(f"  ERROR removing {path}: {e}", file=sys.stderr)

    return {"inserted": inserted, "skipped": skipped, "files_removed": files_removed}


def auto_migrate_if_needed() -> bool:
    """Run migration if the DB is empty and flat files still exist.

    Called automatically on portal startup — seamless first-run experience.
    Returns True if migration ran.
    """
    from src.utils.todos_db import count_todos, DB_PATH

    # DB already has data — no migration needed
    if DB_PATH.exists() and count_todos() > 0:
        return False

    # Check if any flat files still exist
    if not any(p.exists() for p in _all_todo_paths()):
        return False  # Nothing to migrate

    print("First run: auto-migrating TODO flat files → DB...")
    result = migrate(dry_run=False)
    print(
        f"Auto-migration complete: {result['inserted']} todos imported, "
        f"{result['files_removed']} files removed."
    )
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate TODO flat files to todos DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
