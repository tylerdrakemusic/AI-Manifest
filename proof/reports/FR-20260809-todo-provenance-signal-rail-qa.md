# Functional QA Report - FR-20260809-todo-provenance-signal-rail

**Decision:** FAIL
**Agent:** ⊕workspace-qa
**Date:** 2026-08-10
**Perf run:** abb80089-c974-429f-bd58-5d0dce7578c1

## Acceptance Criteria

| # | Acceptance criterion | Test type | Result | Evidence |
|---|---|---|---|---|
| 1 | `perfected_at` is nullable, added by migration, and existing TODO identity and `fr_id` survive. | Focused pytest and compile check | PASS | `31 passed, 1 skipped`; `compileall=PASS` |
| 2 | Approved `perfect-scoped-td` refinement stamps UTC `perfected_at`; denied or failed refinement does not stamp it, and FR linkage remains explicit. | Skill diff inspection and focused regression coverage | PASS with test-gap | Skill specifies the required transaction boundary and independent fields. No executable skill harness was present to exercise approved/denied/failed mutations. |
| 3 | Executive view models preserve TODO IDs and independent `perfected_at` and `fr_id` state; done buttons target the rendered TODO ID. | Focused pytest | PASS | `31 passed, 1 skipped`; assertions cover `TODO #227`, `TODO #228`, both signal labels, and `markDone(227/228, this)`. |
| 4 | Executive Audio Brief Portal Signal rail/evidence stream renders TODO IDs and independent signal states in a running UI, with screenshot proof. | Playwright with fresh server preflight | FAIL | Fresh server returned HTTP 200, then live portal rendered zero TODO IDs because the branch worktree DB has zero open rows. Fixture attempt rendered `#927` and `#928` but failed before completion because `#929` was filtered from the rendered set; the temporary harness then had a syntax error on rerun. Screenshot was captured at the proof path. |

## Focused Commands

```text
C:\G\python.exe f:\⊕Workspace\src\utils\fr_cli.py get FR-20260809-todo-provenance-signal-rail
C:\G\python.exe -m pytest tests/test_todos_db.py tests/test_executive_audio_brief.py -q
31 passed, 1 skipped in 14.27s
C:\G\python.exe -m pytest -q   (Workspace worktree)
627 passed, 13 skipped, 11 deselected, 2 warnings in 37.39s
C:\G\python.exe -m compileall -q src/utils/todos_db.py tools/executive_audio_brief.py
compileall=PASS
git diff --check main...HEAD   (both worktrees)
no output; PASS
```

## Playwright

- Triggered: yes; the AI-Manifest diff changes the portal Python source.
- Preflight: fresh process on port 8200; health URL returned HTTP 200; server was torn down after each attempt.
- Live-data attempt: FAIL, `No TODO IDs rendered in the live portal`.
- Fixture attempt: server health PASS and screenshot capture PASS, but assertions failed because the rendered fixture ID set omitted `#929`; the subsequent harness retry failed before browser execution due an unterminated temporary Python string.
- Screenshot: `proof/screenshots/FR-20260809-todo-provenance-signal-rail-signal-rail.png` (1,025,375 bytes).

## Scope and Security Audit

- AI-Manifest diff: `src/utils/todos_db.py`, `tools/executive_audio_brief.py`, and their focused tests only.
- Workspace diff: `.github/skills/perfect-scoped-td/SKILL.md` only.
- `git diff --check`: PASS for both worktrees.
- No new dependencies, credentials, cross-project source paths, or portal navigation entries detected.
- Temporary fixture DB was restored; production databases were not written.

## Verdict

QA is blocked at `FUNCTIONAL_QA` because the required running-UI criterion lacks a completed PASS proof. Do not transition the FR to `ARCHITECTURE_REVIEW`. Implementation follow-up should provide a populated branch-safe fixture or test seam for the portal and investigate why the third fixture row was omitted before rerunning the browser check.

## Follow-up Proof - 2026-08-10

**Result:** PASS for the previously incomplete running-UI proof. The original failure above is retained as the historical QA result; this addendum records the successful rerun.

- Preflight started `tools/executive_audio_brief.py --serve --port 8200` from the isolated worktree and received HTTP 200 from `/health`.
- The focused Playwright fixture used a temporary SQLite database and inserted exactly three open `workspace` rows with explicit IDs:
	- `TODO #927`: perfected only (`Refined · perfect-scoped-td`, `No FR link`)
	- `TODO #928`: FR-linked only (`Not perfected`, `FR linked`)
	- `TODO #929`: perfected and FR-linked (`Refined · perfect-scoped-td`, `FR linked`)
- DOM assertions verified all three IDs, both independent signal labels for each row, and each row's `markDone(<id>, ...)` target.
- Focused command: `C:\G\python.exe -m pytest tests/test_executive_brief_portal.py -m playwright -k signal_states_render_with_explicit_ids -q`
- Result: `1 passed, 19 deselected in 4.01s`.
- Screenshot: `proof/screenshots/FR-20260809-todo-provenance-signal-rail-signal-rail.png`.
- The temporary database and server were cleaned up; no production database was written. The preflight server was terminated after the test.