# FR-20260812 Executive Todo Cancellation Proof

Date: 2026-08-12
Branch: `feature/FR-20260812-executive-todo-cancellation`

## Focused Regression

`45 passed`:

- `tests/test_todos_db.py`
- `tests/test_todo_done_endpoint.py`
- `tests/test_executive_audio_brief.py`

## Functional QA

Playwright ran with `PLAYWRIGHT_ENABLED=1` after the Executive Brief Portal preflight on port 8200 returned HTTP 200. The cancellation scenarios passed:

- Card-list cancellation with confirmation accepted: row faded/removed and `closure_reason=cancelled` persisted.
- Card-list cancellation with confirmation rejected: row remained open and database state remained open.
- Fully-offloadable table cancellation with confirmation accepted: table row faded/removed and `closure_reason=cancelled` persisted.
- Both surfaces exposed icon-only controls with `title` and `aria-label` attributes.

Command filter: `tests/test_executive_brief_portal.py -m playwright -k cancel_`
Result: `3 passed, 20 deselected`.

## Lifecycle Contract

- Existing checkmark completion writes `done=1`, UTC `closed_at`, and `closure_reason=completed`.
- Cancellation writes `done=1`, UTC `closed_at`, and `closure_reason=cancelled`.
- `get_open_todos()` and `get_done_todos()` continue to use `done=0` and `done=1` visibility semantics.
- Schema migration adds nullable `closure_reason` and permits `completed`, `cancelled`, and `stale` without automatic stale detection.
