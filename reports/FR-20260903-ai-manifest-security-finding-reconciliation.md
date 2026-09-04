# FR-20260903 AI-Manifest Security Finding Reconciliation

Review scope: eight open vulnerability records whose paths are under `f:\👁AI-Manifest\`, queried from the workspace `vulnerabilities` table. Central finding records were not mutated. This report contains no API keys, tokens, database keys, or secret values.

| Finding | Location | Validation and disposition |
| --- | --- | --- |
| `7eedc140b26ad8fd` | `src/utils/todos_db.py:191` | High SQL finding. Table names come from fixed internal migration tuples. Remediated by strict identifier validation and quoted identifiers, with regression coverage. |
| `33173a5b071ff676` | `tests/test_database_backup.py:369` | High SQL finding. Test-only SQLCipher `PRAGMA key` setup uses a local test value and is not production query construction. Confirmed false positive. |
| `9b68623a819d7a16` | `tests/test_ollama_client.py:31` | Low HTTP finding. Local mocked Ollama fixture; no network call. Confirmed false positive. |
| `9b73c9199e59909f` | `tests/test_ollama_client.py:64` | Low HTTP finding. Local environment-override fixture; no transport. Confirmed false positive. |
| `061bfaf8366bdfae` | `tests/test_ollama_client.py:67` | Low HTTP finding. Local mocked URL; no transport. Confirmed false positive. |
| `0a3f7fdb2249aff8` | `tests/test_ollama_client.py:71` | Low HTTP finding. Local mocked URL; no transport. Confirmed false positive. |
| `49b0bf6f1c62adbf` | `tests/test_ollama_client.py:73` | Low HTTP finding. Local mocked URL; no transport. Confirmed false positive. |
| `5b8ade94ea8910bd` | `tests/test_ollama_client.py:74` | Low HTTP finding. Local mocked URL; no transport. Confirmed false positive. |

## Executable evidence

- `pytest tests/test_todos_db.py -k "identifier_quoting or init_db_adds_nullable or init_db_preserves_closure"`: 3 passed.
- `pytest tests/test_database_backup.py tests/test_ollama_client.py tests/test_todos_db.py`: backup and Ollama tests passed; the TODO module passed its migration coverage, then hit an existing long-running test and was interrupted. No failure was reported in the changed behavior.
- Bandit `B608` on implicated files: the original open identifier findings are removed by the validator change. One separate fixed-literal schema-expression warning remains because the scanner cannot model the allowlisted expression selection; it is documented here and was not suppressed in source.
- Editor diagnostics for changed Python files: no errors.

## State

Worktree remediation and individual finding reconciliation are complete. Disposition mutation remains pending the governed final reconciliation step.