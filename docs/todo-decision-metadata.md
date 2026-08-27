# Todo Decision Metadata

AI-Manifest stores the current decision assessment in
`todo_decision_metadata` and every submitted assessment in the append-only
`todo_decision_assessments` history table.

## Contract

Each assessment requires these canonical fields:

- `expected_value`
- `user_or_system_benefit`
- `strategic_alignment`
- `confidence`, an integer from 1 through 10
- `cost_of_delay`
- `primary_benefit_category`
- `benefit_summary`
- `justification`
- `evidence`, a list of non-empty strings

`secondary_benefit_category` is optional. Primary and secondary categories,
when present, must be one of `user`, `system`, `strategic`, `revenue`,
`risk_reduction`, `learning`, `maintenance`, or `compliance`.

Legacy names such as `benefit_category`, `impact_score`,
`confidence_score`, and `rationale` are rejected. The public helper APIs
return only the canonical assessment fields and `evidence` as a list.

## Enforcement

Validation is progressive. Evidence is required for high-impact or oversized
todos, represented by priority 8 through 10 or an `estimated_effort` value of
`large`, `xl`, `x-large`, or `oversized`. Lower-impact assessments can be
recorded without evidence while the decision is still being developed.

## Compatibility

`init_db()` is idempotent and preserves incompatible legacy metadata tables
under a `_legacy` table name before creating the canonical tables. Existing
todos receive no fabricated assessment. Missing metadata remains missing.
Current metadata replacement and historical assessment insertion occur in one
immediate transaction, so each saved assessment is versioned in history.

## Priority

`get_priority_guidance()` returns an advisory recommendation derived from the
current `confidence`. It never changes `todos.priority`. Explicit priority
updates remain bounded to 1 through 10 and append to `priority_history`.