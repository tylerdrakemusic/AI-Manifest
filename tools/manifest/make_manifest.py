#!/usr/bin/env python3
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

print("Starting manifest generation...", file=sys.stderr)

#  Manually list all files to be in manifest
all_files = {
    r"F:\.github\agents\∞life-brainstorm.agent.md": None,
    r"F:\.github\agents\∞life-budget.agent.md": None,
    r"F:\.github\agents\∞life-data-analytics.agent.md": None,
    r"F:\.github\agents\∞life-orchestrator.agent.md": None,
    r"F:\.github\agents\∞life-research.agent.md": None,
    r"F:\.github\agents\∞life-risk.agent.md": None,
    r"F:\.github\agents\⊕workspace-alignment.agent.md": None,
    r"F:\.github\agents\⊕workspace-bench-analyzer.agent.md": None,
    r"F:\.github\agents\⊕workspace-ci.agent.md": None,
    r"F:\.github\agents\⊕workspace-commitment.agent.md": None,
    r"F:\.github\agents\⊕workspace-dashboards.agent.md": None,
    r"F:\.github\agents\⊕workspace-doer.agent.md": None,
    r"F:\.github\agents\⊕workspace-gen-qee.agent.md": None,
    r"F:\.github\agents\⊕workspace-hygiene.agent.md": None,
    r"F:\.github\agents\⊕workspace-overseer.agent.md": None,
    r"F:\.github\agents\⊕workspace-proof.agent.md": None,
    r"F:\.github\agents\⊕workspace-protector.agent.md": None,
    r"F:\.github\agents\⊕workspace-security.agent.md": None,
    r"F:\.github\agents\❤music-catalog.agent.md": None,
    r"F:\.github\agents\❤music-orchestrator.agent.md": None,
    r"F:\.github\agents\❤music-performance.agent.md": None,
    r"F:\.github\agents\❤music-production.agent.md": None,
    r"F:\.github\agents\❤music-signatures.agent.md": None,
    r"F:\.github\agents\⟨ψ⟩quantum-orchestrator.agent.md": None,
    r"F:\.github\agents\⟨ψ⟩quantum-research.agent.md": None,
    r"F:\.github\agents\👁ai-manifest-orchestrator.agent.md": None,
    r"F:\.github\instructions\agent-self-regen.instructions.md": None,
    r"F:\.github\instructions\hygiene-base.instructions.md": None,
    r"F:\.github\instructions\orchestrator-cleanup.instructions.md": None,
    r"F:\.github\instructions\testing-base.instructions.md": None,
    r"F:\.github\instructions\∞life-base.instructions.md": None,
    r"F:\.github\instructions\∞life-health-evaluation.instructions.md": None,
    r"F:\.github\instructions\∞life-python.instructions.md": None,
    r"F:\.github\instructions\❤music-base.instructions.md": None,
    r"F:\.github\instructions\⟨ψ⟩quantum-base.instructions.md": None,
    r"F:\.github\skills\scope-creep\SKILL.md": None,
}

# Compute hashes
for fpath_str in all_files:
    fpath = Path(fpath_str)
    if fpath.exists():
        with open(fpath, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
            all_files[fpath_str] = h
            print(f"  ✓ {fpath.name}: {h[:8]}...", file=sys.stderr)
    else:
        print(f"  ✗ NOT FOUND: {fpath}", file=sys.stderr)

# Build manifest
manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": sum(1 for v in all_files.values() if v),
    "files": {k: v for k, v in all_files.items() if v},
}

# Write
out = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"SUCCESS: {manifest['file_count']} files → {out}", file=sys.stderr)
sys.exit(0)
