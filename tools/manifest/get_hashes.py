import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

# Compute hashes for new files
new_files_to_hash = [
    r"F:\.github\agents\⊕workspace-hygiene.agent.md",
    r"F:\.github\instructions\agent-self-regen.instructions.md",
]

output = []
for fpath_str in new_files_to_hash:
    fpath = Path(fpath_str)
    if fpath.exists():
        with open(fpath, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
            output.append(f"{fpath_str}|{h}")

# Write to temp file
temp_out = Path(r"F:\hash_output.txt")
temp_out.write_text("\n".join(output), encoding="utf-8")
print(f"Hashes written to {temp_out}")
