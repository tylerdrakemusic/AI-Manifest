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

## QA-Blocking Repair

Date: 2026-08-12

- Added `test_init_db_preserves_closure_reason_during_scan_source_migration`.
- The regression failed before the repair because a legacy `cancelled` value became `NULL` during the table rebuild.
- `_migrate_todos_for_scan_source()` now copies `closure_reason` when the legacy column exists and uses `NULL` for schemas that predate it.
- Focused repair suite: `25 passed` across `tests/test_todos_db.py` and `tests/test_todo_done_endpoint.py`.
- Targeted Playwright rerun after port 8200 preflight: `6 passed, 17 deselected` for checkmark and cancellation tests; teardown completed.
- Repair commit: `071fe634e944a044e024ad72865b21259f04d4e0`.
