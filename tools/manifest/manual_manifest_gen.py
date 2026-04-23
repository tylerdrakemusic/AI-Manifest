#!/usr/bin/env python3
"""Manual manifest generation and verification"""
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
EXTENSIONS = {".md", ".py", ".json", ".yaml", ".yml"}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return ""

def build_manifest() -> dict:
    entries = {}
    for watched_dir in WATCHED_DIRS:
        if not watched_dir.exists():
            print(f"Warning: Directory not found: {watched_dir}")
            continue
        for path in sorted(watched_dir.rglob("*")):
            if path.is_file() and path.suffix in EXTENSIONS:
                rel = path.as_posix().replace("f:/", "f:\\")
                hash_val = sha256_file(path)
                if hash_val:
                    entries[str(path)] = hash_val
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "update_manifest.py",
        "file_count": len(entries),
        "files": entries,
    }

# Build the manifest
print("=== BUILDING MANIFEST ===")
manifest = build_manifest()

# Write it
MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✅ Manifest written: {manifest['file_count']} files → {MANIFEST_PATH}")
print(f"   Generated at: {manifest['generated_at']}")

# Now verify
print("\n=== AGENT FILE INTEGRITY CHECK ===")
if not MANIFEST_PATH.exists():
    print("❌ No manifest found.")
else:
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    known = manifest["files"]
    current = build_manifest()["files"]

    new_files = set(current) - set(known)
    missing = set(known) - set(current)
    modified = {p for p in known if p in current and current[p] != known[p]}

    issues = 0
    for p in sorted(new_files):
        print(f"  ⚠️  NEW (not in manifest):      {p}")
        issues += 1
    for p in sorted(missing):
        print(f"  ⚠️  MISSING (was in manifest):  {p}")
        issues += 1
    for p in sorted(modified):
        print(f"  ⚠️  MODIFIED (hash changed):    {p}")
        issues += 1

    if issues == 0:
        print(f"  ✅ All {len(known)} agent files match manifest.")
    else:
        print(f"\n  {issues} integrity issue(s) found.")

# Print the target file hash
print("\n=== TARGET FILE INFORMATION ===")
for file_path, file_hash in manifest['files'].items():
    if 'agent-self-regen.instructions.md' in file_path:
        print(f"File: {file_path}")
        print(f"Hash: {file_hash}")
        print(f"Hash length: {len(file_hash)} characters")
        print(f"Is valid 64-hex: {len(file_hash) == 64 and all(c in '0123456789abcdef' for c in file_hash.lower())}")
        
print(f"\nTotal file_count: {manifest['file_count']}")
