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

## Readability Repair Rerun - 2026-08-11

**Decision:** PASS
**Agent:** ⊕workspace-qa
**Repair commit:** `69c4a7fa096805f3a831de72437e25380e70dd48`
**Perf run:** `c59ce793-db0e-49cd-b693-c8d38f955810`

| # | Acceptance criterion | Test type | Result | Evidence |
|---|---|---|---|---|
| 1 | `perfected_at` is nullable, added by migration, and existing TODO identity and `fr_id` survive. | Focused pytest and compile check | PASS | AI-Manifest focused regressions: `34 passed`; `compileall=PASS`. |
| 2 | Approved `perfect-scoped-td` refinement stamps UTC `perfected_at`; denied or failed refinement does not stamp it, and FR linkage remains explicit. | Skill contract and regression inspection | PASS with test-gap | Workspace skill diff preserves independent `perfected_at` and `fr_id` fields and approved transaction behavior. No executable skill harness exists for denied/failed mutation paths. |
| 3 | Executive view models preserve TODO IDs and independent `perfected_at` and `fr_id` state; done buttons target the rendered TODO ID. | Focused pytest | PASS | Focused AI-Manifest regressions: `34 passed`; browser assertions verify exact `markDone(927/928/929, this)` targets. |
| 4 | Executive Audio Brief Portal Signal rail/evidence stream renders TODO IDs and independent signal states in a running UI, with screenshot proof. | Fresh server preflight and exact Playwright test | PASS | Port 8200 `/health`: HTTP 200. `test_signal_states_render_with_explicit_ids`: `1 passed, 19 deselected`; desktop `1280x2422` and mobile `390x3474` screenshots. |

## Rerun Checks

- AI-Manifest worktree: `git diff main...HEAD --check` PASS; scoped files are the expected migration, portal implementation, focused tests, and QA report.
- Workspace worktree: `git diff main...HEAD --check` PASS; only `.github/skills/perfect-scoped-td/SKILL.md` is changed.
- AI-Manifest source and tests: `compileall=PASS`.
- Fresh server teardown: PASS; temporary fixture database and server were cleaned up; production databases were not written.
- Screenshot proof: [desktop](../screenshots/FR-20260809-todo-provenance-signal-rail-desktop.png), [mobile](../screenshots/FR-20260809-todo-provenance-signal-rail-mobile.png).

## Residual Test Debt

- The broader Workspace portal suite remains environmentally unrelated to this FR: `627 passed, 7 skipped, 6 failed, 11 deselected`. Failures include legacy generated output expecting 3 cards while current output has 6 and the configured ElevenLabs key returning no voices; these were not changed because they do not affect the repaired Signal rail acceptance criteria.
- The AC2 denied/failed refinement paths remain a test-coverage gap; the skill contract and independent field behavior pass inspection, but no executable skill harness is present.

## Rerun Verdict

All four acceptance criteria have PASS evidence for the repaired readability commit. Advance the FR to `ARCHITECTURE_REVIEW`.

## Focused Follow-up QA - 2026-08-11

**Decision:** PASS for the requested readability follow-up checks; no FR state transition performed.
**Agent:** ⊕workspace-qa
**Perf run:** `6185e601-78cb-48cd-922c-1bfae95ad6ce`

| # | Requested check | Result | Evidence |
|---|---|---|---|
| 1 | Fresh Executive Audio Brief server preflight | PASS | Port 8200 was cleared, fresh worktree server PID 33240 started, and `/` returned HTTP 200. Server teardown completed after browser checks. |
| 2 | Desktop `1280x900`: rendered TODO text precedes `.todo-meta`; `.todo-text` has positive readable bounds and no overflow | PASS | 24/24 live rows passed DOM order, positive bounding-box, and text overflow assertions; horizontal page overflow was false. |
| 3 | Mobile `390x844`: same readability and ordering checks | PASS | 24/24 live rows passed DOM order, positive bounding-box, and text overflow assertions; document scroll width was exactly 390. |
| 4 | Summary keeps completion stats and omits duplicate `Top priorities:` text | PASS | Live summary included open/completed percentage stats; `Top priorities:` was absent. |
| 5 | TODO IDs, independent provenance signals, FR independence, and `markDone(id, this)` remain intact | PASS | Focused provenance fixture tests passed; live rows retained unique TODO IDs and exact `markDone(<id>, this)` handlers. |
| 6 | Focused Python tests | PASS with unrelated suite caveat | Targeted subset: `6 passed, 32 deselected`. Broader focused suites: `37 passed, 1 failed`; the failure is existing `test_three_status_cards_rendered`, which expects 3 cards while the generated portal contains 6. |

### Proof Artifacts

- Desktop screenshot: [FR-20260809-todo-provenance-signal-rail-followup-desktop-1280x900.png](../screenshots/FR-20260809-todo-provenance-signal-rail-followup-desktop-1280x900.png)
- Mobile screenshot: [FR-20260809-todo-provenance-signal-rail-followup-mobile-390x844.png](../screenshots/FR-20260809-todo-provenance-signal-rail-followup-mobile-390x844.png)
- Proof IDs: `51b1adb96714`, `686872cb088f`, `0824524e8a79`, `2446c7231148`, `798fdb72fe41`

### Scope

No production code, database, or FR state was modified by QA. The only worktree changes observed besides the pre-existing readability refinement were the two proof screenshots and this report append. No merge was performed.