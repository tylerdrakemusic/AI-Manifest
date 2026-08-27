# FR-20260827 Workspace Todo Decision Metadata Standard

## Implementation Handoff

- FR: `FR-20260827-workspace-todo-decision-metadata-standard`
- Repository: `tylerdrakemusic/AI-Manifest`
- Branch: `feature/FR-20260827-workspace-todo-decision-metadata-standard`
- Base: `main`
- Scope: AI-Manifest integration boundary for workspace TODO decision metadata
- Companion repository: `tylerdrakemusic/-Workspace`
- Status: approved handoff; implementation intentionally not started

This baseline hands the approved FR to implementation. The implementation
should identify every AI-Manifest TODO decision-metadata read or write
boundary, consume the workspace-wide contract without duplicating it, and add
focused regression proof for supported, missing, and malformed metadata.
Existing integrations and unrelated TODO behavior remain unchanged.

The implementation must preserve public-repository hygiene, contain no
health, financial, credential, or generated runtime data, and coordinate with
the workspace contract through the matching handoff artifact. The final
implementation should document compatibility behavior and executable
validation results in the FR ledger.

This commit is a branch baseline only. It contains no feature implementation,
schema mutation, generated data, credentials, or sensitive records.