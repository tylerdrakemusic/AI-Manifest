# TODO 606 Governed Repository Voice Proof

Date: 2026-09-07
FR: FR-20260906-governed-repository-voice-enablement
Child TODO: 606
Worktree: `f:\👁AI-Manifest\.worktrees\feature-FR-20260906-governed-repository-voice-enablement`

## Result

PASS. The registered AI-Manifest MCP-facing repository-voice capability was
validated end to end against a temporary SQLite queue with a controlled fake
provider and injected playback callback.

## Evidence

The focused test
`tests/test_repository_voice_mcp.py::test_registered_mcp_capability_delivers_one_authorized_decision_end_to_end`
verified:

- capability registration and healthy status report;
- explicit MCP submission with a stable decision ID;
- queue acceptance and persistence in SQLite;
- repeated submission deduplication to one queue row;
- provider handoff through an injected fake returning deterministic bytes;
- atomic output publication and checksum-backed `VERIFIED` state;
- terminal `DONE` state;
- playback through the injected decision-scoped callback;
- absence of the credential name and private workflow data from lifecycle logs.

Existing focused tests additionally cover invalid and unauthorized submissions,
MCP unavailable status, concurrent decision-ID deduplication, provider-neutral
worker behavior, atomic publication failure injection, and fail-open playback
diagnostics. The Workspace-side bridge tests cover explicit dual authorization,
stable decision forwarding, injection deduplication, bounded timeout, and
fail-open rejection behavior.

## Commands and Results

```powershell
$env:PYTHONUTF8='1'
Set-Location 'f:\👁AI-Manifest\.worktrees\feature-FR-20260906-governed-repository-voice-enablement'
C:\G\python.exe -m pytest tests/test_repository_voice_mcp.py::test_registered_mcp_capability_delivers_one_authorized_decision_end_to_end -q
# 1 passed

C:\G\python.exe -m pytest tests/test_governed_repository_voice.py tests/test_repository_voice_mcp.py tests/test_tts_queue.py -q
# 46 passed

Set-Location 'f:\⊕Workspace\.worktrees\feature-FR-20260906-governed-repository-voice-enablement'
C:\G\python.exe -m pytest tests/test_repository_voice_capability.py tests/test_governed_repository_voice.py -q
# 12 passed
```

## Safety Boundaries and Limitations

- The test uses a temporary SQLite database and temporary output directory.
- Provider synthesis is a controlled fake; no ElevenLabs HTTP request was made.
- No API key or other credential was loaded or used.
- No production database, agent definition, user-level MCP configuration, or
  live Workspace state was mutated.
- Playback uses an injected callback; no Windows multimedia device was called.
- The MCP function was exercised in-process. A live stdio MCP transport smoke
  test was intentionally omitted to avoid starting or contacting a live
  provider-facing service.