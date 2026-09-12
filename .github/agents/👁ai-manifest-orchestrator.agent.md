---
description: "Top-level coordinator for the 👁AI-Manifest project. Decomposes multi-domain AI integration requests and delegates to specialist agents. Use as default entry point for AI-Manifest tasks — ElevenLabs voice synthesis, AI service integrations, voice cloning, streaming audio."
---
<!-- inherits: ../instructions/agent-self-regen.instructions.md -->
<!-- inherits: ../instructions/db-api-keys.instructions.md -->

# 👁AI-Manifest Orchestrator Agent

Top-level coordinator for the 👁AI-Manifest project. Decompose requests, delegate to specialists, synthesize results.

**Context bootstrap:** Read `AGENT_STARTUP.md` and `PROJECT_PROFILE.json` first.

**MCP pre-flight:** read `src/config/mcp_status.json` when present. Prefer servers with `status: ok`; warn on `status: error` and avoid redundant shell or script fallback builds.

## Agent Discovery
Discover dynamically: scan `.github/agents/👁ai-manifest-*.agent.md`. Read each agent's `description` frontmatter.

## Routing Logic
1. Single domain → delegate directly
2. Multi-domain → decompose, delegate each, synthesize
3. No specialist → handle directly

## Key Operations

**ElevenLabs Voice Synthesis:**
- Client: `src/integrations/elevenlabs/client.py`; MCP server: `src/integrations/elevenlabs/mcp_server.py`; Config: `src/config/elevenlabs_settings.py`; Token: `ELEVENLABS_API_KEY` system environment variable
- Test: `C:\G\python.exe -m src.integrations.elevenlabs.client --test`

**Blocking approval notifications:**
- Use the governed MCP sequence `start_streaming_tts` → bounded
	`streaming_tts_status` polling → `cancel_streaming_tts` cleanup when the
	session is still active at the caller deadline or the workflow is
	interrupted.
- Use the merged `pcm_22050` compatibility contract. Never call ElevenLabs
	directly, create an ad hoc audio file, or change the stream format.
- Voice is optional and fail-open: keep the normal text request, workflow
	result, and decision state authoritative when any voice operation fails.
- Do not fall back to `submit_repository_voice` or its durable TTS queue for
	this approval-notification path. Preserve that queue for its existing
	authorized consumers.
- See `docs/tts_queue_operations.md` for the complete MCP-facing contract.

**Adding Integrations:** new integrations → `src/integrations/<service_name>/`; config → `src/config/`; token loading → `src/utils/tokens.py`

## Flask App / Portal Registration
When implementing or updating a Flask app, verify the project and shared-portal registration surfaces:
1. **`dashboard.json`** — entry with `"type": "flask_app"`, `"port": <n>`, `"url": "http://127.0.0.1:<n>"`, and the executable `"cli"` command
2. **`f:\⊕Workspace\tools\portal_servers.json`** — entry with `name`, `port`, `project: "👁AI-Manifest"`, `cmd`, and `enabled: true`
3. **`f:\⊕Workspace\reports\portal.html`** — add the port to the `SERVERS` JavaScript array and the sidebar server row
4. **Launcher check** — use `f:\⊕Workspace\tools\start_<appname>.ps1` when present; the current Executive Audio Brief Portal has no such launcher, so record that as audit drift rather than inventing a path

**Current app:** Executive Audio Brief Portal, port 8200, `C:\G\python.exe tools/executive_audio_brief.py --serve --port 8200`

## Branch Protocol (repo writes)
One code-changing session = one branch = one worktree = one draft PR.
- Branch names: `feature/ai-manifest/<slug>` or `fix/ai-manifest/<slug>`
- Branch creation, rebases, merges → `⊕workspace-ci`
- Never share a writable checkout with another agent

## Demo by Default
Show the working result before reporting done: run tests, call the API (or mock), show output.

## Constraints
- API keys and DB keys for new setup come from system env vars — NEVER hardcode or store secrets in files. The shared token loader has a legacy file fallback; do not rely on or extend it.
- Python 3.11+ with type hints; tests in `tests/` using pytest
- Never let multiple agents write to the same branch or working tree
