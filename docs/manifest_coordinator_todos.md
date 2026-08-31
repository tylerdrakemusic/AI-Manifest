# Manifest coordinator todo operations

The coordination MCP is the governed interface for manifest todos. It only
accepts allowlisted operations and rejects arbitrary database or SQL arguments.

When the MCP transport is unavailable, local callers may use
`src.utils.todos_db` directly as a safe fallback. The fallback uses the
repository-local `src/data/manifest_todos.db`, runs schema migrations through
`init_db()`, and preserves the same confirmation, optimistic-version,
idempotency, prerequisite, terminal-state, and metadata validation rules.

Mutating fallback calls must remain inside an explicit SQLite transaction. Do
not substitute another database, accept raw SQL, or bypass confirmation and
version preconditions. Use `get_todo_graph()` after a mutation for structured
read-back verification.

Protected todo fields are immutable after creation: `id`, `project`, `source`,
`created_at`, `parent_id`, and FR linkage. Existing todos can update only
allowlisted rich fields with an authenticated caller and matching `updated_at`
value. Child batches require a confirmed idempotency key; retries return the
original child ids without creating duplicates.