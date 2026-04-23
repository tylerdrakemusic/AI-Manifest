#!/usr/bin/env python3
"""
Regenerate agent manifest with SHA-256 hashes
This script can be run independently without subprocess
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        print(f"Error hashing {path}: {e}")
        raise

def main():
    # Paths
    WATCHED_DIRS = [
        Path(r"f:\.github\agents"),
        Path(r"f:\.github\instructions"),
        Path(r"f:\.github\skills"),
    ]
    MANIFEST_PATH = Path(r"f:\.github\!!☾⛧security\agent-manifest.json")
    EXTENSIONS = {".md", ".py", ".json", ".yaml", ".yml"}
    
    # Read old manifest
    print("Reading old manifest...")
    old_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    old_files = set(old_manifest["files"].keys())
    print(f"  Old manifest had {old_manifest['file_count']} files")
    
    # Build new manifest
    print("\nScanning current files...")
    entries: dict[str, str] = {}
    for watched_dir in WATCHED_DIRS:
        if not watched_dir.exists():
            print(f"  Skipping non-existent: {watched_dir}")
            continue
        print(f"  Scanning: {watched_dir}")
        for path in sorted(watched_dir.rglob("*")):
            if path.is_file() and path.suffix in EXTENSIONS:
                hash_val = sha256_file(path)
                entries[str(path)] = hash_val
                print(f"    {path.name}: {hash_val[:16]}...")
    
    new_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "update_manifest.py",
        "file_count": len(entries),
        "files": entries,
    }
    print(f"\n  New manifest has {new_manifest['file_count']} files")
    
    # Compute delta
    new_files_set = set(new_manifest["files"].keys())
    added = sorted(new_files_set - old_files)
    removed = sorted(old_files - new_files_set)
    potentially_modified = sorted(old_files & new_files_set)
    modified = [p for p in potentially_modified 
                if old_manifest["files"][p] != new_manifest["files"][p]]
    
    # Convert to repo-relative paths
    def to_repo_relative(path: str) -> str:
        path_lower = path.lower()
        if path_lower.startswith("f:\\"):
            return path[3:]
        return path
    
    added_rel = [to_repo_relative(p) for p in added]
    removed_rel = [to_repo_relative(p) for p in removed]
    modified_rel = [to_repo_relative(p) for p in modified]
    
    # Write new manifest
    print(f"\nWriting new manifest...")
    MANIFEST_PATH.write_text(
        json.dumps(new_manifest, indent=2, ensure_ascii=False), 
        encoding="utf-8"
    )
    print(f"  ✅ Manifest written to {MANIFEST_PATH}")
    
    # Print delta report
    print(f"\n{'='*70}")
    print(f"MANIFEST DELTA REPORT")
    print(f"{'='*70}")
    print(f"\nOld file_count: {old_manifest['file_count']}")
    print(f"New file_count: {new_manifest['file_count']}")
    print(f"\nADDED ({len(added_rel)} files):")
    for p in added_rel:
        print(f"  + {p}")
    if not added_rel:
        print("  (none)")
    
    print(f"\nREMOVED ({len(removed_rel)} files):")
    for p in removed_rel:
        print(f"  - {p}")
    if not removed_rel:
        print("  (none)")
    
    print(f"\nMODIFIED ({len(modified_rel)} files):")
    for p in modified_rel:
        print(f"  M {p}")
    if not modified_rel:
        print("  (none)")
    
    print(f"\n{'='*70}")
    print(f"SUMMARY:")
    print(f"  Total changes: {len(added_rel) + len(removed_rel) + len(modified_rel)}")
    print(f"  Only manifest file modified in this operation: YES")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
