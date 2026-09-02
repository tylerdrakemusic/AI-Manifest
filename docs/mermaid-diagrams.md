# AI-Manifest Mermaid diagrams

The canonical AI-Manifest Mermaid sources live in `diagrams/`:

- `manifest-architecture.mmd` is the owning overview.
- `manifest-db-schema.mmd` documents the coordination data model.
- `manifest-tech-stack.mmd` documents the runtime and integration layers.
- `manifest-derived-media-pipeline.mmd` is derived from the architecture overview.
- `manifest-derived-todo-and-backup.mmd` is derived from the architecture overview.

The two derived views retain their `Traceability.parent` markers, and the
architecture overview lists both derived paths. The shared Workspace inventory
may continue to index these files for cross-repository discovery, but ownership
and edits belong to this repository. The local rendering-budget test protects
the five-source set, UTF-8 readability, and derived-view lineage.