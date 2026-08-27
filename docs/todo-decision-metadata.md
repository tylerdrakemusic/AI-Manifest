# Todo Decision Metadata

## Contract Boundary

The Workspace-owned contract is exchanged through identical, versioned,
repository-local manifests at `src/contracts/todo_decision_metadata.v1.json`.
AI-Manifest loads its local manifest through `src/utils/todo_decision_contract.py`
and Workspace loads its own through the same-shaped local loader. Neither
repository imports code or reads files from the other at runtime. The Workspace
parity test compares the parsed JSON artifacts and fails if either snapshot
drifts; the ownership test also fails if a validator stops deriving its rules
from its local manifest.

The manifest is a contract snapshot, not a second persistence schema. Each
repository may store current and append-only history in its own database shape,
provided its public API emits and accepts the manifest's normalized payload.

AI-Manifest stores the current decision assessment in
`todo_decision_metadata` and every submitted assessment in the append-only
`todo_decision_assessments` history table.

## Contract

Each assessment requires these canonical fields. Every field in `SCORE_FIELDS`
is an integer from 1 through 10:

- `expected_value`
- `user_or_system_benefit`
- `strategic_alignment`
- `confidence`
- `cost_of_delay`
- `primary_benefit_category`
- `benefit_summary`
- `justification`
- `evidence`, a list of non-empty strings

`secondary_benefit_category` is optional. Primary and secondary categories,
when present, must be one of `user`, `system`, `strategic`, `revenue`,
`risk_reduction`, `learning`, `maintenance`, or `compliance`.

The canonical scale is exposed as `SCALE_ANCHORS` and on normalized metadata:
`1` minimal, `3` low, `5` moderate, `7` strong, `8` high, `9` very high, and
`10` exceptional.

Legacy names such as `benefit_category`, `impact_score`,
`confidence_score`, and `rationale` are rejected. The public helper APIs
return only the canonical assessment fields and `evidence` as a list.

## Enforcement

Validation is progressive. Evidence is required when any score is 8 or higher,
and two evidence items are required when any score is 9 or higher. Lower-impact
assessments can be recorded without evidence while the decision is still being
developed. TODO priority and estimated effort do not change metadata validation.

## Compatibility

`init_db()` is idempotent and preserves incompatible legacy metadata tables
under a `_legacy` table name before creating the canonical tables. Existing
todos receive no fabricated assessment. Missing metadata remains missing.
Current metadata replacement and historical assessment insertion occur in one
immediate transaction, so each saved assessment is versioned in history.

## Priority

`get_priority_guidance()` returns an advisory recommendation derived from the
mean of the five canonical scores. It never changes `todos.priority`. Explicit
priority updates remain bounded to 1 through 10 and append to `priority_history`.