#!/usr/bin/env python
# -*- coding: utf-8 -*-
import hashlib
import os

files_to_hash = [
    # Agents (26 files)
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
    
    # Instructions (9 files)
    r"F:\.github\instructions\agent-self-regen.instructions.md",
    r"F:\.github\instructions\hygiene-base.instructions.md",
    r"F:\.github\instructions\orchestrator-cleanup.instructions.md",
    r"F:\.github\instructions\testing-base.instructions.md",
    r"F:\.github\instructions\∞life-base.instructions.md",
    r"F:\.github\instructions\∞life-health-evaluation.instructions.md",
    r"F:\.github\instructions\∞life-python.instructions.md",
    r"F:\.github\instructions\❤music-base.instructions.md",
    r"F:\.github\instructions\⟨ψ⟩quantum-base.instructions.md",
    
    # Skill (1 file)
    r"F:\.github\skills\scope-creep\SKILL.md",
]

print("SHA-256 Hashes:")
print("=" * 80)

for filepath in files_to_hash:
    try:
        with open(filepath, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            print(f"{file_hash}  {filepath}")
    except FileNotFoundError:
        print(f"ERROR: File not found - {filepath}")
    except Exception as e:
        print(f"ERROR: {filepath} - {str(e)}")

print("=" * 80)
print(f"Total files processed: {len(files_to_hash)}")
