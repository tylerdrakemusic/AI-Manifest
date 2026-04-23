#!/usr/bin/env python3
# Direct manifest builder
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def compute_hash(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

files_to_process = [
    r"F:\.github\agents\∞life-brainstorm.agent.md",
    r"F:\.github\agents\∞life-budget.agent.md",
    r"F:\.github\agents\∞life-data-analytics.agent.md",
    r"F:\.github\agents\∞life-orchestrator.agent.md",
    r"F:\.github\agents\∞life-research.agent.md",
    r"F:\.github\agents\∞life-risk.agent.md",
    r"F:\.github\agents\⊕workspace-alignment.agent.md",
    r"F:\.github\agents\⊕workspace-bench-analyzer.agent.md",
    r"F:\.github\agents\⊕workspace-ci.agent.md",
    r"F:\.github\agents\⊕workspace-commitment.agent.md",
    r"F:\.github\agents\⊕workspace-dashboards.agent.md",
    r"F:\.github\agents\⊕workspace-doer.agent.md",
    r"F:\.github\agents\⊕workspace-gen-qee.agent.md",
    r"F:\.github\agents\⊕workspace-hygiene.agent.md",
    r"F:\.github\agents\⊕workspace-overseer.agent.md",
    r"F:\.github\agents\⊕workspace-proof.agent.md",
    r"F:\.github\agents\⊕workspace-protector.agent.md",
    r"F:\.github\agents\⊕workspace-security.agent.md",
    r"F:\.github\agents\❤music-catalog.agent.md",
    r"F:\.github\agents\❤music-orchestrator.agent.md",
    r"F:\.github\agents\❤music-performance.agent.md",
    r"F:\.github\agents\❤music-production.agent.md",
    r"F:\.github\agents\❤music-signatures.agent.md",
    r"F:\.github\agents\⟨ψ⟩quantum-orchestrator.agent.md",
    r"F:\.github\agents\⟨ψ⟩quantum-research.agent.md",
    r"F:\.github\agents\👁ai-manifest-orchestrator.agent.md",
    r"F:\.github\instructions\agent-self-regen.instructions.md",
    r"F:\.github\instructions\hygiene-base.instructions.md",
    r"F:\.github\instructions\orchestrator-cleanup.instructions.md",
    r"F:\.github\instructions\testing-base.instructions.md",
    r"F:\.github\instructions\∞life-base.instructions.md",
    r"F:\.github\instructions\∞life-health-evaluation.instructions.md",
    r"F:\.github\instructions\∞life-python.instructions.md",
    r"F:\.github\instructions\❤music-base.instructions.md",
    r"F:\.github\instructions\⟨ψ⟩quantum-base.instructions.md",
    r"F:\.github\skills\scope-creep\SKILL.md",
]

manifest_files = {}
for fpath_str in sorted(files_to_process):
    fpath = Path(fpath_str)
    try:
        if fpath.exists():
            h = compute_hash(fpath)
            manifest_files[fpath_str] = h
            print(f"[OK] {fpath.name}")
        else:
            print(f"[SKIP] {fpath_str} - not found")
    except Exception as e:
        print(f"[ERROR] {fpath_str}: {e}")

manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(manifest_files),
    "files": manifest_files,
}

out_path = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"\n[SUCCESS] Manifest written: {len(manifest_files)} files")
print(f"Location: {out_path}")
