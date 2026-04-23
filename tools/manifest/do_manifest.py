import hashlib, json, subprocess
from pathlib import Path
from datetime import datetime, timezone

# Get all files by finding them
agents_dir = Path(r"F:\.github\agents")
instr_dir = Path(r"F:\.github\instructions")
skills_dir = Path(r"F:\.github\skills")

files = {}
for d in [agents_dir, instr_dir, skills_dir]:
    if d.exists():
        for f in d.rglob("*"):
            if f.is_file() and f.suffix in {".md", ".py", ".json", ".yaml", ".yml"}:
                with open(f, "rb") as fp:
                    h = hashlib.sha256(fp.read()).hexdigest()
                files[str(f)] = h

manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(files),
    "files": files,
}

dest = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✅ Updated manifest: {len(files)} files")
for line in [f for f in files if "agents" in f]:
    print(f"  A: {Path(line).name}")
