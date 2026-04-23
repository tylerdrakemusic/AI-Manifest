#!/usr/bin/env python3
"""Generate agent manifest with SHA-256 hashes."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def sha256_file(filepath):
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# Agent files (26 total)
agents = [
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

# Instruction files (9 total)
instructions = [
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

# Skills files (1 total)
skills = [
    "scope-creep/SKILL.md",
]

manifest_files = {}

# Process agents
for agent in sorted(agents):
    filepath = Path(f"F:\\.github\\agents\\{agent}")
    if filepath.exists():
        full_path = str(filepath)
        manifest_files[full_path] = sha256_file(filepath)

# Process instructions
for instruction in sorted(instructions):
    filepath = Path(f"F:\\.github\\instructions\\{instruction}")
    if filepath.exists():
        full_path = str(filepath)
        manifest_files[full_path] = sha256_file(filepath)

# Process skills
for skill in sorted(skills):
    filepath = Path(f"F:\\.github\\skills\\{skill}")
    if filepath.exists():
        full_path = str(filepath)
        manifest_files[full_path] = sha256_file(filepath)

manifest = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "generated_by": "update_manifest.py",
    "file_count": len(manifest_files),
    "files": manifest_files,
}

# Write manifest
manifest_path = Path(r"F:\.github\!!☾⛧security\agent-manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"✅ Manifest written: {manifest['file_count']} files")
print(f"   Generated at: {manifest['generated_at']}")
print(f"   Agents: {len([x for x in manifest_files if 'agents' in x])}")
print(f"   Instructions: {len([x for x in manifest_files if 'instructions' in x])}")
print(f"   Skills: {len([x for x in manifest_files if 'skills' in x])}")
