import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# Configuration
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

# Write new manifest
MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

# Compute delta
new_files_set = set(new_manifest["files"].keys())
added = sorted(new_files_set - old_files)
removed = sorted(old_files - new_files_set)
modified = [p for p in sorted(old_files & new_files_set) 
            if old_manifest["files"][p] != new_manifest["files"][p]]

# Convert to repo-relative paths
to_rel = lambda p: p[3:] if p.lower().startswith("f:\\") else p
added_rel = [to_rel(p) for p in added]
removed_rel = [to_rel(p) for p in removed]
modified_rel = [to_rel(p) for p in modified]

# Output results
print("="*70)
print("MANIFEST REGENERATION COMPLETE")
print("="*70)
print(f"\nOld file_count: {old_manifest['file_count']}")
print(f"New file_count: {new_manifest['file_count']}")
print(f"\nADDED ({len(added_rel)}):")
for p in added_rel: print(f"  + {p}")
print(f"\nREMOVED ({len(removed_rel)}):")
for p in removed_rel: print(f"  - {p}")
print(f"\nMODIFIED ({len(modified_rel)}):")
for p in modified_rel: print(f"  M {p}")
print(f"\n{'='*70}")
print(f"Manifest written: {MANIFEST_PATH}")
print(f"Total delta: {len(added_rel) + len(removed_rel) + len(modified_rel)} files changed")
print("="*70)
