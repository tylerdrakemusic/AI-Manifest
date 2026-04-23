import json
from datetime import datetime, timezone
import hashlib
from pathlib import Path

# Load old manifest
old_path = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
old_manifest = json.loads(old_path.read_text(encoding="utf-8"))

# Files to remove (these don't exist anymore)
remove_files = [
    r"f:\.github\agents\∞life-hygiene.agent.md",
    r"f:\.github\agents\❤music-hygiene.agent.md",
    r"f:\.github\agents\⟨ψ⟩quantum-hygiene.agent.md",
    r"f:\.github\agents\👁ai-manifest-hygiene.agent.md",
]

# New files to add (with hash computation)
new_files_paths = [
    r"F:\.github\agents\⊕workspace-hygiene.agent.md",
    r"F:\.github\instructions\agent-self-regen.instructions.md",
]

# Start with old files minus removed
new_files_dict = {k: v for k, v in old_manifest["files"].items() 
                  if k.lower() not in [r.lower() for r in remove_files]}

# Add new files
for fpath_str in new_files_paths:
    fpath = Path(fpath_str)
    if fpath.exists():
        h = hashlib.sha256(fpath.read_bytes()).hexdigest()
        # Use lowercase f:\ to match format
        key = str(fpath).lower().replace("f:", "f:").replace("\\", "\\")
        new_files_dict[key] = h

# Build new manifest
new_manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(new_files_dict),
    "files": new_files_dict,
}

# Write
with open(old_path, "w", encoding="utf-8") as f:
    json.dump(new_manifest, f, indent=2, ensure_ascii=False)

print(f"OK: {len(new_files_dict)} files")
