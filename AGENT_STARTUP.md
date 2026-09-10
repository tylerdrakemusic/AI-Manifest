# ⚡ AGENT STARTUP DIRECTIVE — 👁AI-Manifest

**READ THIS FIRST.** Context bootstrap for any AI agent picking up work on the 👁AI-Manifest project.

---

## 1. Gather Context

```
1. Read this file completely
2. Read PROJECT_PROFILE.json for current project state
3. Read README.md for navigation and architecture context
4. Read src/config/mcp_status.json when present
```

## 2. Project Location & Key Paths

| Resource | Path |
|----------|------|
| **Project Root** | `f:\👁AI-Manifest\` |
| **Workspace Root** | `f:\` |
| **Parent Repo** | `tylerdrakemusic/AI-Manifest` (public GitHub repository) |
| **Python Executable** | `C:\G\python.exe` |
| **Agent Definitions** | `.github/agents/👁ai-manifest-*.agent.md` |
| **Instructions** | `.github/agents/👁ai-manifest-*.agent.md` and workspace instructions |
| **System Specs** | `f:\⊕Workspace\SYSTEM_SPECS.md` |

### 👁AI-Manifest Agents (`.github/agents/`)

All 👁AI-Manifest agents are prefixed `👁ai-manifest-` and live at `.github/agents/👁ai-manifest-*.agent.md`. **Scan that glob to discover available agents.**

| Agent | Purpose |
|-------|---------|
| **👁ai-manifest-orchestrator** | Top-level coordinator. Decomposes requests, delegates, synthesizes. Default entry point. |

> **Adding agents:** Create `.github/agents/👁ai-manifest-<name>.agent.md` with a keyword-rich `description` in frontmatter.

## 3. Project Summary

**👁AI-Manifest** is Tyler James Drake's AI integration platform. It provides:
- **ElevenLabs voice synthesis** — text-to-speech, voice cloning, real-time voice transmission
- **AI service integrations** — centralized hub for external AI API connections

### ElevenLabs Access
- **API Key:** Set `ELEVENLABS_API_KEY` in Windows System Environment Variables; never store credentials in repository files. The token loader retains a legacy file fallback for compatibility, but new setup and agent workflows must use the environment variable.
- **Primary use:** Voice synthesis, voice cloning, streaming audio

## 4. Key Data

| Asset | Path | Notes |
|-------|------|-------|
| **Source code** | `src/` | Core modules, integrations, utilities |
| **ElevenLabs integration** | `src/integrations/elevenlabs/` | Voice API client |
| **Config** | `src/config/` | API settings, voice presets |
| **Tests** | `tests/` | pytest test suite |
| **Research** | `research/` | AI integration research notes |
| **Docs** | `docs/` | Architecture, protocols, API docs |

## 5. Rules

- Use system environment variables for all new credential setup — NEVER hardcode or store secrets in files. `src/utils/tokens.py` still contains a legacy file fallback for compatibility; do not rely on or extend that fallback.
- Python 3.11+ with type hints on all function signatures
- Docstrings on public functions only
- Tests in `tests/` using pytest
- Research notes in `research/` as markdown
