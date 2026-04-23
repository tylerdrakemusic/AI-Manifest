#!/usr/bin/env python3
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def sha256_file(filepath):
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha256_hash.update(data)
    return sha256_hash.hexdigest()

# Known files based on grep results
files_dict = {}

# Process all files in the directories
base_dirs = [
    (r"F:\.github\agents", "agents"),
    (r"F:\.github\instructions", "instructions"),
    (r"F:\.github\skills", "skills"),
]

for base_path_str, dir_type in base_dirs:
    base_path = Path(base_path_str)
    if base_path.exists():
        for file_path in sorted(base_path.rglob("*")):
            if file_path.is_file() and file_path.suffix in {".md", ".py", ".json", ".yaml", ".yml"}:
                try:
                    file_hash = sha256_file(file_path)
                    # Use full path with backslashes as keys
                    full_path_key = str(file_path)
                    files_dict[full_path_key] = file_hash
                    print(f"✓ {dir_type}: {file_path.name}")
                except Exception as e:
                    print(f"✗ Error processing {file_path.name}: {e}")

manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(files_dict),
    "files": files_dict,
}

# Write the new manifest
manifest_path = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"\n✅ Manifest updated!")
print(f"   Total files: {len(files_dict)}")
print(f"   Location: {manifest_path}")
print(f"   Generated at: {manifest['generated_at']}")

# Count by type
agents = [x for x in files_dict if "agents" in x]
instructions = [x for x in files_dict if "instructions" in x]
skills = [x for x in files_dict if "skills" in x]
print(f"   Agents: {len(agents)}")
print(f"   Instructions: {len(instructions)}")
print(f"   Skills: {len(skills)}")
