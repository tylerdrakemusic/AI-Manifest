# Architecture Impact Report: FR-20260923-ai-manifest-capability-registry

**Decision:** PASS (recycled light review)

## Recycled Review

The recycled change is limited to `ProviderManifest.to_dict()`: authentication
configuration metadata is checked against the approved non-secret descriptor
allowlist before serialization. The public model shape, registry ownership,
MCP function signatures, offline behavior, and provider manifests are
unchanged. The change introduces no new architectural impact, dependency,
diagram staleness, cross-project scope, or public API/security regression.

The prior automated-review finding is resolved by focused regression coverage
for both direct manifest serialization and the MCP-facing provider lookup.

## Scope

- The complete feature surface is limited to the 👁AI-Manifest worktree.
- Changed files are the README, capability registry contract/docs, typed
  models, repository-owned manifests, deterministic registry, read-only MCP
  adapter, focused tests, and `diagrams/manifest-architecture.mmd`.
- No dependency manifest changed. No cross-project imports or `sys.path`
  shims were introduced.

## Architecture Assessment

- Typed contracts cover providers, capabilities, models, constraints,
  authentication requirements, and manifest version metadata.
- Four offline manifests register DALL-E 3, ElevenLabs, Hugging Face, and
  Pollinations. They do not add generation behavior or live provider calls.
- `CapabilityRegistry` owns sorting, filtering, lookup, and deterministic
  not-found behavior. The MCP tools delegate to it and do not duplicate
  lookup logic.
- Serialization exposes repository-owned metadata only. No credential values,
  masked credentials, health, quota, freshness, routing, readiness, or
  generation state is returned.
- The new discovery contract is separate from the existing live
  `provider_health.py` readiness contract and follows the existing FastMCP
  integration pattern.

## Diagram Status

| Diagram | Status | Notes |
| --- | --- | --- |
| `diagrams/manifest-architecture.mmd` | UPDATED | Names the versioned offline `CapabilityRegistry` manifests and read-only capability MCP tools. |
| `diagrams/diagram-manifest.json` | CURRENT | Existing ownership and derived-view lineage remain valid; no new source or derived view is required. |
| Workspace agent topology/integrations diagrams | NOT AFFECTED | No new agent, cross-project integration, or shared dependency was introduced. |
| Scheduler architecture inventory/diagram | CURRENT | No scheduler change; deterministic scheduler coverage remains complete. |

Budget and lineage validation passed. Mermaid fallback renderer evidence:
`mermaid.ink HTTP`, 47/47 diagrams rendered successfully. No renderer
blocker was found.

## Validation

- 👁 focused capability and affected-diagram tests: 9 passed.
- Workspace scheduler, federation, and diagram-budget tests: 27 passed.
- Complete diagram renderer: 47/47 rendered successfully via `mermaid.ink HTTP`.
- `git diff --check`: passed.

No architecture blockers remain. The FR may advance to `REVIEW_REQUESTED`.
No merge was performed.