# FR-20260426: Executive Audio Brief Panel

**Status:** Implementation in progress  
**Branch:** `feature/ai-manifest/executive-audio-brief-panel`  
**Date opened:** 2026-04-26

## Summary

Per-project TODO + human TODO audio brief via ElevenLabs TTS.
Reads `TODO_AI.md` and `TODO_TYLER.md` from all 5 workspace projects,
synthesizes an executive audio brief, and surfaces it in a clean portal panel.

## Acceptance Criteria

1. Reads both `TODO_AI.md` AND `TODO_TYLER.md` from all 5 projects → ElevenLabs TTS audio
2. Audio saved to `output/briefs/` with timestamped filename
3. `executive_brief_portal.html` shows per-project TODO summaries in clean executive panel layout
4. Embedded audio player for the generated brief
5. One-click Regenerate button (no manual steps)
6. Panel linked from ⊕Workspace unified portal/dashboard
7. Existing `src/integrations/elevenlabs/client.py` reused — no new TTS code
