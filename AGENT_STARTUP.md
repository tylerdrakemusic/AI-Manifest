# ⚡ AGENT STARTUP DIRECTIVE — 👁AI-Manifest

**READ THIS FIRST.** Context bootstrap for any AI agent picking up work on the 👁AI-Manifest project.

---

## 1. Gather Context

```
1. Read this file completely
2. Read TODO_AI.md for current agentic task queue
3. Read TODO_TYLER.md for pending human actions and blockers
4. Read PROJECT_PROFILE.json for current project state
5. Read README.md for architecture context if needed
```

## 2. Project Location & Key Paths

| Resource | Path |
|----------|------|
| **Project Root** | `f:\executedcode\👁AI-Manifest\` |
| **Workspace Root** | `f:\` |
| **Parent Repo** | `f:\executedcode\` (private git repo — source controlled) |
| **Python Executable** | `C:\G\python.exe` |
| **Agent Definitions** | `f:\.github\agents\👁ai-manifest-*.agent.md` |
| **Instructions** | `f:\.github\instructions\👁ai-manifest-*.instructions.md` |
| **System Specs** | `f:\SYSTEM_SPECS.md` |

### 👁AI-Manifest Agents (`f:\.github\agents\`)

All 👁AI-Manifest agents are prefixed `👁ai-manifest-` and live at `f:\.github\agents\👁ai-manifest-*.agent.md`. **Scan that glob to discover available agents.**

| Agent | Purpose |
|-------|---------|
| **👁ai-manifest-orchestrator** | Top-level coordinator. Decomposes requests, delegates, synthesizes. Default entry point. |

> **Adding agents:** Create `f:\.github\agents\👁ai-manifest-<name>.agent.md` with a keyword-rich `description` in frontmatter.

## 3. Project Summary

**👁AI-Manifest** is Tyler James Drake's AI integration platform. It provides:
- **ElevenLabs voice synthesis** — text-to-speech, voice cloning, real-time voice transmission
- **AI service integrations** — centralized hub for external AI API connections

### ElevenLabs Access
- **API Key:** Store in `f:\executedcode\tokens\elevenlabs` (NOT checked in)
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

- All API keys loaded from `f:\executedcode\tokens/` — NEVER hardcode secrets
- Python 3.11+ with type hints on all function signatures
- Docstrings on public functions only
- Tests in `tests/` using pytest
- Research notes in `research/` as markdown
