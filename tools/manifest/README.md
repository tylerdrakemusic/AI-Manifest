# tools/manifest — Agent Manifest Tooling

These scripts were collected from drift at the `F:\` drive root and consolidated here.
They were generated incrementally by AI agents during `.github/!!☾⛧security/agent-manifest.json` regeneration sessions.

## Canonical Tool

The authoritative manifest regeneration script is:

```
F:\.github\!!☾⛧security\update_manifest.py
```

## Archive Contents

The scripts in this directory represent iteration history across multiple manifest-regen sessions:

| Category | Files |
|----------|-------|
| **Hash computation** | `compute_hashes.py`, `compute_hashes.sh`, `get_hashes.py`, `get_hashes.ps1`, `get_sha256.bat`, `hash_compute.py`, `HASH_COMPUTATION.txt` |
| **Manifest generation** | `manifest_generator.py`, `make_manifest.py`, `build_manifest_direct.py`, `gen.py`, `do_manifest.py`, `standalone_manifest.py`, `final_manifest.py`, `manual_manifest_gen.py`, `compute_manifest.py` |
| **Manifest regeneration** | `regenerate_manifest.py`, `regen_manifest_temp.py`, `exec_regen.py`, `execute_manifest_regen.py`, `final_regen_manifest.py`, `run_regen.py`, `RUN_IT.py`, `temp_run_manifest.py`, `minimal_update.py`, `update_existing_manifest.py` |
| **Verification** | `verify_manifest.py`, `verify_inline.py`, `full_manifest_verification.py`, `integrity_check.py`, `run_verify.py` |
| **Execution helpers** | `runner.py`, `wrapper.py`, `run_commands.py`, `run_both_commands.py`, `run_and_read.py`, `run_manifest.bat`, `run_standalone.bat`, `inline_hash.bat`, `run_commands_temp.bat` |
| **Tests** | `test_execution.py`, `test_shell_exec.py` |
| **Docs / output** | `INSTRUCTIONS_FOR_CALLING_AGENT.txt`, `push_output.txt` |

## Notes

- Most files are functionally redundant; keep for historical reference
- Future manifest work should use only the canonical tool above
- See `👁AI-Manifest` project for the broader AI integration platform
