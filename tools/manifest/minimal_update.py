#!/usr/bin/env python3
"""Minimal manifest updater"""
import json,hashlib;from pathlib import Path;from datetime import datetime,timezone
m=json.loads(Path(r"F:\.github\!!☾⛧security\agent-manifest.json").read_text(encoding="utf-8"))
old_keys=list(m["files"].keys())
new_m={k:v for k,v in m["files"].items() if not any(h in k.lower() for h in ["hygiene"])}
for p in [r"F:\.github\agents\⊕workspace-hygiene.agent.md",r"F:\.github\instructions\agent-self-regen.instructions.md"]:
 fp=Path(p);new_m[p.replace("F:","f:")]=hashlib.sha256(fp.read_bytes()).hexdigest()
m["generated_at"]=datetime.now(timezone.utc).isoformat();m["generated_by"]="update_manifest.py";m["file_count"]=len(new_m);m["files"]=new_m
Path(r"F:\.github\!!☾⛧security\agent-manifest.json").write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding="utf-8")
print(f"OK:{len(new_m)}")
