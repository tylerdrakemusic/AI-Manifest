#!/usr/bin/env python3
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WATCHED_DIRS = [
    Path(r"f:\.github\agents"),
    Path(r"f:\.github\instructions"),
    Path(r"f:\.github\skills"),
]
MANIFEST_PATH = Path(r"f:\.github\!!☾⛧security\agent-manifest.json")
EXTENSIONS = {".md", ".py", ".json", ".yaml", ".yml"}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# Read old manifest
old_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
old_files = set(old_manifest["files"].keys())
old_count = len(old_files)

# Build new manifest
entries = {}
for watched_dir in WATCHED_DIRS:
    if not watched_dir.exists():
        continue
    for path in sorted(watched_dir.rglob("*")):
        if path.is_file() and path.suffix in EXTENSIONS:
            entries[str(path)] = sha256_file(path)

new_manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(entries),
    "files": entries,
}
new_files = set(entries.keys())

# Write new manifest
MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

# Calculate changes
added = new_files - old_files
removed = old_files - new_files
modified = {p for p in old_files if p in new_files and entries[p] != old_manifest["files"][p]}

print("=== MANIFEST REGENERATION COMPLETE ===")
print(f"Old file_count: {old_count}")
print(f"New file_count: {len(entries)}")
print(f"\nAdded ({len(added)}):")
for p in sorted(added):
    repo_path = p.replace("f:\\", ".\\")
    print(f"  {repo_path}")
print(f"\nRemoved ({len(removed)}):")
for p in sorted(removed):
    repo_path = p.replace("f:\\", ".\\")
    print(f"  {repo_path}")
print(f"\nModified ({len(modified)}):")
for p in sorted(modified):
    repo_path = p.replace("f:\\", ".\\")
    print(f"  {repo_path}")

# Count by type
agents = [p for p in new_files if "agents" in p]
instructions = [p for p in new_files if "instructions" in p]
skills = [p for p in new_files if "skills" in p]

print(f"\n=== FILE COUNTS ===")
print(f"Agents: {len(agents)}")
print(f"Instructions: {len(instructions)}")
print(f"Skills: {len(skills)}")
print(f"Total: {len(entries)}")
