# Temporary script to regenerate manifest
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

WATCHED_DIRS = [
    Path(r"f:\.github\agents"),
    Path(r"f:\.github\instructions"),
    Path(r"f:\.github\skills"),
]
MANIFEST_PATH = Path(r"f:\.github\!!☾⛧security\agent-manifest.json")
OLD_MANIFEST_PATH = Path(r"f:\.github\!!☾⛧security\agent-manifest-old.json")
EXTENSIONS = {".md", ".py", ".json", ".yaml", ".yml"}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def build_manifest() -> dict:
    entries: dict[str, str] = {}
    for watched_dir in WATCHED_DIRS:
        if not watched_dir.exists():
            continue
        for path in sorted(watched_dir.rglob("*")):
            if path.is_file() and path.suffix in EXTENSIONS:
                entries[str(path)] = sha256_file(path)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "update_manifest.py",
        "file_count": len(entries),
        "files": entries,
    }

# Read old manifest for comparison
old_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
old_files = set(old_manifest["files"].keys())

# Build new manifest
new_manifest = build_manifest()
new_files_set = set(new_manifest["files"].keys())

# Compute delta
added = sorted(new_files_set - old_files)
removed = sorted(old_files - new_files_set)
potentially_modified = sorted(old_files & new_files_set)
modified = [p for p in potentially_modified if old_manifest["files"][p] != new_manifest["files"][p]]

# Convert paths to repo-relative backslash format
def to_repo_relative(path: str) -> str:
    # Convert f:\.github\... to .github\...
    path = path.lower()
    if path.startswith("f:\\"):
        return path[3:]
    return path

added_rel = [to_repo_relative(p) for p in added]
removed_rel = [to_repo_relative(p) for p in removed]
modified_rel = [to_repo_relative(p) for p in modified]

# Write new manifest
MANIFEST_PATH.write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

# Print results
print(f"=== MANIFEST REGENERATION RESULTS ===")
print(f"Old file_count: {old_manifest['file_count']}")
print(f"New file_count: {new_manifest['file_count']}")
print(f"")
print(f"ADDED ({len(added_rel)}):")
for p in added_rel:
    print(f"  + {p}")
print(f"")
print(f"REMOVED ({len(removed_rel)}):")
for p in removed_rel:
    print(f"  - {p}")
print(f"")
print(f"MODIFIED ({len(modified_rel)}):")
for p in modified_rel:
    print(f"  M {p}")
print(f"")
print(f"✅ Manifest written to {MANIFEST_PATH}")
