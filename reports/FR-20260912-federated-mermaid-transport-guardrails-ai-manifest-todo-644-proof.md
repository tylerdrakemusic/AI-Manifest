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

## Scoped Repair

- Removed the over-scoped local production/helper/verification additions that
  landed after commit 6c8080733243b9e0842b11a106f2856729791b20.
- Kept the TODO 644 diagram and manifest changes intact.
- Replaced the cross-repo production import with a tests-only helper at
  tests/diagram_budget_helpers.py so the diagram tests still validate local
  source bytes, nodes, edges, category budgets, split metadata, and reciprocal
  lineage without any runtime-module addition.

## Validation

Focused tests:

```powershell
Set-Location 'F:\👁AI-Manifest\.worktrees\fix-FR-20260912-federated-mermaid-transport-guardrails'
$env:PYTHONUTF8='1'
C:\G\python.exe -m pytest tests/test_diagram_manifest.py tests/test_mermaid_diagram_rendering_budget.py -q
# 4 passed
```

Exact runner in workflow env:

```powershell
Set-Location 'F:\👁AI-Manifest\.worktrees\fix-FR-20260912-federated-mermaid-transport-guardrails'
Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
$env:WORKSPACE_ROOT='F:\⊕Workspace'
$env:WORKSPACE_BACKUP_ENGINE_PATH='F:\⊕Workspace\src\utils\database_backup.py'
C:\G\python.exe tools\run_tests.py --parallel --junitxml=tmp\pytest-junit.xml
```

Runner result:

- `pytest-xdist` loaded after clearing the stray shell override.
- The run still terminated with `KeyboardInterrupt` after worker startup and
  before test execution completed.
- JUnit output was written to tmp/pytest-junit.xml and remains uncommitted.

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