## ⊕ Architecture Impact Report — FR-20260913-ai-manifest-tts-dispatch-quota-playback-serialization
**Decision:** PASS_WITH_UPDATES

### Diff Impact

| File in diff | Impact type | Affected diagram |
| --- | --- | --- |
| `src/services/tts_dispatch_coordinator.py` | New shared quota and playback coordinator | `diagrams/manifest-architecture.mmd`, `diagrams/manifest-derived-media-pipeline.mmd` |
| `src/services/tts_queue_worker.py` | Durable provider admission and playback lease wiring | `diagrams/manifest-architecture.mmd` |
| `src/services/streaming_tts.py` | Streaming quota/playback lifecycle and cleanup | `diagrams/manifest-architecture.mmd`, `diagrams/manifest-derived-media-pipeline.mmd` |
| `src/integrations/elevenlabs/mcp_server.py` | Synchronous and streaming MCP coordinator integration | `diagrams/manifest-architecture.mmd`, `diagrams/manifest-derived-media-pipeline.mmd` |
| `diagrams/manifest-architecture.mmd` | Updated parent architecture view | N/A |
| `diagrams/manifest-derived-media-pipeline.mmd` | Updated derived media pipeline view | N/A |

### Contract Review

- Shared process-wide coordinator covers durable, streaming, and synchronous paths.
- Quota admission is fail-closed for missing, stale, malformed, or exhausted snapshots and accounts for outstanding reservations.
- Playback leases cover the complete local playback lifetime and release on success, cancellation, failure, and shutdown cleanup.
- Durable queue default wiring preserves explicit coordinator injection and `coordinator=None` opt-out behavior; built-in provider admission uses the shared coordinator.
- No dependency, SQLite schema, cross-project import, credential-storage, or secret-redaction boundary was added or weakened.
- Existing PCM, deduplication, retry, ambiguous-outcome reconciliation, path validation, and fail-open approval-voice contracts remain represented by focused tests.
- Related FRs were not modified: synchronous playback remains `CHANGES_REQUESTED`; provider-neutral reconciliation remains `SOAKING`.

### Diagram Status

| Diagram | Status | Notes |
| --- | --- | --- |
| `diagrams/manifest-architecture.mmd` | UPDATED | Coordinator, quota snapshot, and process-wide playback lease are represented; within the established node budget. |
| `diagrams/manifest-derived-media-pipeline.mmd` | UPDATED | Streaming and synchronous playback edges point to the shared coordinator; lineage parent is `manifest-architecture.mmd`. |
| `F:\⊕Workspace\diagrams\workspace-agent-topology.mmd` | PASS | All 23 workspace agent files have corresponding topology nodes. |
| `F:\⊕Workspace\diagrams\workspace-scheduler-architecture.mmd` | PASS | Inventory remains unchanged; no external scheduler or schedule field was introduced. |

Renderer evidence: `diagrams_dashboard.py --no-open` used the `mermaid.ink HTTP` backend and rendered the affected views successfully. One unrelated pre-existing fallback remained for `capital-db-schema` because of the URI-length limit.

Focused evidence: AI-Manifest diagram/coordinator tests `5 passed`; shared topology/federation contracts `22 passed`; full focused TTS QA was recorded in the ledger as `126 passed` with one pre-existing live test deselected. Full collection remains blocked by the unrelated `WORKSPACE_ROOT` or `WORKSPACE_BACKUP_ENGINE_PATH` requirement in `tests/test_database_backup.py`.

Publication note: the complete implementation and test diff is present in the requested isolated worktree, but the feature branch ref still points at `origin/main` and there is no PR. `⊕workspace-ci` must commit and publish the worktree diff before review/merge can continue.