# AI-Manifest TODO 644 Proof

Date: 2026-09-12
FR: FR-20260912-federated-mermaid-transport-guardrails
Parent TODO: 644
Repository: manifest
Worktree: F:\👁AI-Manifest\.worktrees\fix-FR-20260912-federated-mermaid-transport-guardrails

## Scope

Repair only the AI-Manifest-owned measured Mermaid budget violations under the
shared federated transport and budget contract, without advancing the parent
workflow.

## Findings

The shared diagram validator reported two actual AI-Manifest budget violations
before repair:

- diagrams/manifest-architecture.mmd: overview node budget exceeded, 41 nodes
  vs 40 allowed.
- diagrams/manifest-derived-media-pipeline.mmd: detail node budget exceeded, 55
  nodes vs 50 allowed.

No AI-Manifest source exceeded the current transport byte limit after
compression, so this repair was limited to local node-budget and split-driven
manifest corrections.

## Repair

- Reduced the parent architecture overview to an architecture summary by moving
  the portal-specific detail out of the overview.
- Split the portal and image-generation relationships into a new derived view:
  diagrams/manifest-derived-portal-and-image.mmd.
- Reduced diagrams/manifest-derived-media-pipeline.mmd to the audio and
  streaming slice only.
- Preserved parent and derived traceability in Mermaid comments and in
  diagrams/diagram-manifest.json.
- Updated manifest metadata to the measured fallback risk and current derived
  view set.

## Validation

Focused tests:

```powershell
Set-Location 'F:\👁AI-Manifest\.worktrees\fix-FR-20260912-federated-mermaid-transport-guardrails'
$env:PYTHONUTF8='1'
C:\G\python.exe -m pytest tests/test_diagram_manifest.py tests/test_mermaid_diagram_rendering_budget.py -q
# 4 passed
```

Measured post-repair budget results:

- diagrams/manifest-architecture.mmd: 40 nodes, 48 edges, 4818 bytes,
  compliant, split_required=false
- diagrams/manifest-db-schema.mmd: 14 nodes, 0 edges, 6053 bytes, compliant,
  split_required=false
- diagrams/manifest-derived-media-pipeline.mmd: 43 nodes, 43 edges, 3663
  bytes, compliant, split_required=false
- diagrams/manifest-derived-portal-and-image.mmd: 13 nodes, 18 edges, 1499
  bytes, compliant, split_required=false
- diagrams/manifest-derived-todo-and-backup.mmd: 19 nodes, 23 edges, 2587
  bytes, compliant, split_required=false
- diagrams/manifest-tech-stack.mmd: 30 nodes, 35 edges, 4076 bytes, compliant,
  split_required=false

## Limitations

- The canonical FR record was read successfully through fr_cli.py, but the
  expected todo CLI entry point was not present at F:\⊕Workspace\src\utils\todo_cli.py.
- A direct sqlite3 probe against src/data/manifest_todos.db did not expose a
  readable todos table in this worktree, so TODO 644 could not be re-read from
  that local database path.
- This repository-local proof does not complete TODO 644 globally and does not
  advance the parent TODO or FR state.