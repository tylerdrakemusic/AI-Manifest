import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# File list from grep output
agent_files = [
    "∞life-brainstorm.agent.md",
    "∞life-budget.agent.md",
    "∞life-data-analytics.agent.md",
    "∞life-orchestrator.agent.md",
    "∞life-research.agent.md",
    "∞life-risk.agent.md",
    "⊕workspace-alignment.agent.md",
    "⊕workspace-bench-analyzer.agent.md",
    "⊕workspace-ci.agent.md",
    "⊕workspace-commitment.agent.md",
    "⊕workspace-dashboards.agent.md",
    "⊕workspace-doer.agent.md",
    "⊕workspace-gen-qee.agent.md",
    "⊕workspace-hygiene.agent.md",
    "⊕workspace-overseer.agent.md",
    "⊕workspace-proof.agent.md",
    "⊕workspace-protector.agent.md",
    "⊕workspace-security.agent.md",
    "❤music-catalog.agent.md",
    "❤music-orchestrator.agent.md",
    "❤music-performance.agent.md",
    "❤music-production.agent.md",
    "❤music-signatures.agent.md",
    "⟨ψ⟩quantum-orchestrator.agent.md",
    "⟨ψ⟩quantum-research.agent.md",
    "👁ai-manifest-orchestrator.agent.md",
]

instr_files = [
    "agent-self-regen.instructions.md",
    "hygiene-base.instructions.md",
    "orchestrator-cleanup.instructions.md",
    "testing-base.instructions.md",
    "∞life-base.instructions.md",
    "∞life-health-evaluation.instructions.md",
    "∞life-python.instructions.md",
    "❤music-base.instructions.md",
    "⟨ψ⟩quantum-base.instructions.md",
]

skill_files = [
    "scope-creep/SKILL.md",
]

files_dict = {}
base = Path(r"F:\.github")

for fname in agent_files:
    fpath = base / "agents" / fname
    if fpath.exists():
        with open(fpath, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
            files_dict[str(fpath)] = h

for fname in instr_files:
    fpath = base / "instructions" / fname
    if fpath.exists():
        with open(fpath, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
            files_dict[str(fpath)] = h

for fname in skill_files:
    fpath = base / "skills" / fname
    if fpath.exists():
        with open(fpath, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
            files_dict[str(fpath)] = h

manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(files_dict),
    "files": files_dict,
}

out = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"OK: {len(files_dict)} files")
