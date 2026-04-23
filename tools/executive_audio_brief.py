"""Executive Audio Brief Portal — ElevenLabs-powered project status briefing.

Gathers cross-project status from TODO files and profiles, ranks top 3
priorities (always including ❤Music), synthesizes an executive audio
brief via ElevenLabs, and serves an interactive HTML portal.

Usage:
    python tools/executive_audio_brief.py                  # Generate brief + HTML
    python tools/executive_audio_brief.py --serve          # Generate + launch portal
    python tools/executive_audio_brief.py --serve --port 8200
    python tools/executive_audio_brief.py --text-only      # Print script, skip TTS
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path(r"f:\\")
OUTPUT_DIR = PROJECT_ROOT / "output" / "briefs"
REPORT_PATH = PROJECT_ROOT / "output" / "executive_brief_portal.html"

# Add workspace root to path for shared integrations
_WORKSPACE_ROOT = Path(r"f:\⊕Workspace")
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# Add project root to path for any remaining project-local imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.elevenlabs import ElevenLabsClient
from src.integrations.elevenlabs.settings import DEFAULT_MODEL_ID

# ---------------------------------------------------------------------------
# Project definitions — discovery order
# ---------------------------------------------------------------------------
PROJECTS = [
    {
        "sigil": "❤",
        "name": "Music",
        "key": "music",
        "root": WORKSPACE_ROOT / "❤Music",
        "always_include": True,
        "priority_weight": 10,  # boosted
    },
    {
        "sigil": "∞",
        "name": "Life",
        "key": "life",
        "root": WORKSPACE_ROOT / "∞Life",
        "always_include": False,
        "priority_weight": 5,
    },
    {
        "sigil": "⟨ψ⟩",
        "name": "Quantum",
        "key": "quantum",
        "root": WORKSPACE_ROOT / "⟨ψ⟩Quantum",
        "always_include": False,
        "priority_weight": 3,
    },
    {
        "sigil": "👁",
        "name": "AI-Manifest",
        "key": "ai_manifest",
        "root": WORKSPACE_ROOT / "👁AI-Manifest",
        "always_include": False,
        "priority_weight": 2,
    },
    {
        "sigil": "⊕",
        "name": "Workspace",
        "key": "workspace",
        "root": WORKSPACE_ROOT / "⊕Workspace",
        "always_include": False,
        "priority_weight": 1,
    },
]

# ---------------------------------------------------------------------------
# Status collection
# ---------------------------------------------------------------------------

def _read_file_safe(path: Path, max_lines: int = 80) -> str:
    """Read a file safely, return empty string on failure."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[:max_lines]
        return "\n".join(lines)
    except Exception:
        return ""


def _read_json_safe(path: Path) -> dict:
    """Read a JSON file safely, return empty dict on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_todo_items(todo_text: str) -> list[str]:
    """Extract unchecked TODO items from markdown."""
    items = []
    for line in todo_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            items.append(stripped[5:].strip())
    return items


def _extract_done_items(todo_text: str) -> list[str]:
    """Extract checked items."""
    items = []
    for line in todo_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            items.append(stripped[5:].strip())
    return items


def gather_project_status(project: dict) -> dict[str, Any]:
    """Gather status for a single project."""
    root = project["root"]
    status: dict[str, Any] = {
        "sigil": project["sigil"],
        "name": project["name"],
        "key": project["key"],
        "exists": root.exists(),
        "always_include": project["always_include"],
        "priority_weight": project["priority_weight"],
        "ai_todos": [],
        "ai_done": [],
        "tyler_todos": [],
        "tyler_done": [],
        "profile": {},
        "summary": "",
        "active_tasks": 0,
        "completed_tasks": 0,
    }

    if not root.exists():
        status["summary"] = f"{project['sigil']}{project['name']}: Project directory not found."
        return status

    # Read TODO_AI.md
    ai_todo_text = _read_file_safe(root / "TODO_AI.md")
    status["ai_todos"] = _extract_todo_items(ai_todo_text)
    status["ai_done"] = _extract_done_items(ai_todo_text)
    status["active_tasks"] += len(status["ai_todos"])
    status["completed_tasks"] += len(status["ai_done"])

    # Read TODO_TYLER.md
    tyler_todo_text = _read_file_safe(root / "TODO_TYLER.md")
    status["tyler_todos"] = _extract_todo_items(tyler_todo_text)
    status["tyler_done"] = _extract_done_items(tyler_todo_text)
    status["active_tasks"] += len(status["tyler_todos"])
    status["completed_tasks"] += len(status["tyler_done"])

    # Read profile (PROJECT_PROFILE.json, ARTIST_PROFILE.json, or SUBJECT_PROFILE.json)
    for profile_name in ["PROJECT_PROFILE.json", "ARTIST_PROFILE.json", "SUBJECT_PROFILE.json"]:
        profile_path = root / profile_name
        if profile_path.exists():
            status["profile"] = _read_json_safe(profile_path)
            break

    # Build summary
    total = status["active_tasks"] + status["completed_tasks"]
    pct = round(100 * status["completed_tasks"] / total) if total > 0 else 0
    top_todos = status["ai_todos"][:3] + status["tyler_todos"][:2]
    summary_lines = [
        f"{project['sigil']}{project['name']}: {status['active_tasks']} open tasks, "
        f"{status['completed_tasks']} completed ({pct}% done)."
    ]
    if top_todos:
        summary_lines.append("Top priorities: " + "; ".join(top_todos[:3]) + ".")
    status["summary"] = " ".join(summary_lines)

    return status


def gather_all_statuses() -> list[dict[str, Any]]:
    """Gather status from all projects."""
    return [gather_project_status(p) for p in PROJECTS]


# ---------------------------------------------------------------------------
# Priority ranking — always include ❤Music
# ---------------------------------------------------------------------------

def rank_projects(statuses: list[dict]) -> list[dict]:
    """Rank projects by priority, ensuring ❤Music is always in top 3."""
    # Score = active_tasks * priority_weight
    for s in statuses:
        s["score"] = s["active_tasks"] * s["priority_weight"]
        if s["always_include"]:
            s["score"] += 1000  # ensure inclusion

    ranked = sorted(statuses, key=lambda s: s["score"], reverse=True)
    return ranked[:3]


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------

def generate_brief_script(top3: list[dict], timestamp: str) -> str:
    """Generate the spoken executive brief text."""
    lines = [
        f"Executive Project Brief — {timestamp}.",
        "",
        "Good day, Tyler. Here's your priority status update.",
        "",
    ]

    for i, proj in enumerate(top3, 1):
        lines.append(f"Priority {i}: {proj['sigil']} {proj['name']}.")
        lines.append(proj["summary"])
        lines.append("")

    # Closing
    total_open = sum(p["active_tasks"] for p in top3)
    lines.append(
        f"Across your top 3 priorities, you have {total_open} open tasks. "
        "Focus on the highest-impact items first. End of brief."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audio synthesis
# ---------------------------------------------------------------------------

def synthesize_brief(
    script: str,
    voice_id: str | None = None,
    output_path: Path | None = None,
) -> Path:
    """Synthesize the brief script to an MP3 file via ElevenLabs."""
    client = ElevenLabsClient()

    # Pick a voice — use provided or first available
    if not voice_id:
        voices = client.list_voices()
        # Prefer a voice named containing "Tyler" or first professional voice
        voice_id = voices[0]["voice_id"] if voices else None
        for v in voices:
            if "tyler" in v["name"].lower() or "drake" in v["name"].lower():
                voice_id = v["voice_id"]
                break

    if not voice_id:
        raise RuntimeError("No ElevenLabs voices available")

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"brief_{ts}.mp3"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    client.save_speech(script, voice_id, output_path)
    return output_path


def list_available_voices() -> list[dict]:
    """Return available ElevenLabs voices."""
    try:
        client = ElevenLabsClient()
        voices = client.list_voices()
        return [{"voice_id": v["voice_id"], "name": v["name"]} for v in voices]
    except Exception as e:
        print(f"Warning: Could not fetch voices: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# HTML portal generation
# ---------------------------------------------------------------------------

def _status_card_html(proj: dict, rank: int) -> str:
    """Generate an HTML card for a project status."""
    sigil = html.escape(proj["sigil"])
    name = html.escape(proj["name"])
    summary = html.escape(proj["summary"])
    active = proj["active_tasks"]
    done = proj["completed_tasks"]
    total = active + done
    pct = round(100 * done / total) if total > 0 else 0

    top_todos_html = ""
    all_todos = (proj["ai_todos"][:3] + proj["tyler_todos"][:2])[:4]
    if all_todos:
        items = "".join(f"<li>{html.escape(t)}</li>" for t in all_todos)
        top_todos_html = f"<ul class='todo-list'>{items}</ul>"

    badge_class = "badge-1" if rank == 1 else ("badge-2" if rank == 2 else "badge-3")

    return f"""
    <div class="status-card">
        <div class="card-header">
            <span class="priority-badge {badge_class}">#{rank}</span>
            <span class="project-sigil">{sigil}</span>
            <h3>{name}</h3>
        </div>
        <div class="progress-bar-container">
            <div class="progress-bar" style="width: {pct}%"></div>
            <span class="progress-label">{done}/{total} tasks ({pct}%)</span>
        </div>
        <p class="summary">{summary}</p>
        {top_todos_html}
    </div>
    """


def generate_portal_html(
    top3: list[dict],
    script: str,
    audio_path: Path | None,
    voices: list[dict],
    all_statuses: list[dict],
    timestamp: str,
) -> str:
    """Generate the full interactive portal HTML."""
    cards_html = "\n".join(
        _status_card_html(p, i) for i, p in enumerate(top3, 1)
    )

    # Voice selector options
    voice_options = "\n".join(
        f'<option value="{html.escape(v["voice_id"])}">{html.escape(v["name"])}</option>'
        for v in voices
    )
    if not voice_options:
        voice_options = '<option value="">No voices available</option>'

    # Audio player section
    audio_section = ""
    if audio_path and audio_path.exists():
        # Encode audio as base64 for inline playback
        import base64
        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        audio_section = f"""
        <div class="audio-player">
            <h3>🔊 Latest Executive Brief</h3>
            <audio id="briefAudio" controls preload="auto">
                <source src="data:audio/mpeg;base64,{audio_b64}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
            <div class="audio-meta">
                Generated: {html.escape(timestamp)} | File: {html.escape(audio_path.name)}
            </div>
        </div>
        """
    else:
        audio_section = """
        <div class="audio-player">
            <h3>🔊 Executive Brief</h3>
            <p class="no-audio">No audio generated yet. Click "Generate Audio Brief" below.</p>
        </div>
        """

    # Script display
    script_escaped = html.escape(script)

    # All projects summary table
    all_rows = ""
    for s in all_statuses:
        sigil = html.escape(s["sigil"])
        name = html.escape(s["name"])
        active = s["active_tasks"]
        done = s["completed_tasks"]
        total = active + done
        pct = round(100 * done / total) if total > 0 else 0
        in_brief = "✅" if s in top3 else ""
        all_rows += f"""
        <tr>
            <td>{sigil} {name}</td>
            <td>{active}</td>
            <td>{done}</td>
            <td>{pct}%</td>
            <td>{in_brief}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>👁 Executive Audio Brief Portal</title>
<style>
:root {{
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --accent: #58a6ff;
    --accent-green: #3fb950;
    --accent-orange: #d29922;
    --accent-red: #f85149;
    --accent-purple: #bc8cff;
    --music-pink: #ff6b9d;
    --radius: 12px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
}}
.container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem;
}}
header {{
    text-align: center;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
}}
header h1 {{
    font-size: 2rem;
    background: linear-gradient(135deg, var(--accent), var(--accent-purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
}}
header .subtitle {{
    color: var(--text-muted);
    font-size: 0.95rem;
}}
.timestamp {{
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-top: 0.5rem;
}}

/* Audio Player */
.audio-player {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin-bottom: 2rem;
    text-align: center;
}}
.audio-player h3 {{
    margin-bottom: 1rem;
    font-size: 1.2rem;
}}
.audio-player audio {{
    width: 100%;
    max-width: 600px;
    margin: 0 auto;
    display: block;
}}
.audio-meta {{
    color: var(--text-muted);
    font-size: 0.8rem;
    margin-top: 0.75rem;
}}
.no-audio {{
    color: var(--text-muted);
    font-style: italic;
}}

/* Controls */
.controls {{
    display: flex;
    gap: 1rem;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 0.5rem;
    padding: 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}}
.serve-hint {{
    text-align: center;
    font-size: 0.85rem;
    color: #c0a060;
    background: #2a2010;
    border: 1px solid #604020;
    border-radius: var(--radius);
    padding: 0.6rem 1.2rem;
    margin-bottom: 1.5rem;
}}
.controls select, .controls button {{
    font-size: 0.9rem;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
}}
.controls button {{
    background: linear-gradient(135deg, var(--accent), var(--accent-purple));
    border: none;
    font-weight: 600;
    color: #fff;
    transition: opacity 0.2s;
}}
.controls button:hover {{
    opacity: 0.85;
}}
.controls button:disabled {{
    opacity: 0.5;
    cursor: wait;
}}
.controls label {{
    color: var(--text-muted);
    font-size: 0.85rem;
}}

/* Status Cards */
.cards-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}}
.status-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    transition: border-color 0.2s;
}}
.status-card:hover {{
    border-color: var(--accent);
}}
.card-header {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}}
.card-header h3 {{
    font-size: 1.1rem;
}}
.project-sigil {{
    font-size: 1.4rem;
}}
.priority-badge {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    font-size: 0.75rem;
    font-weight: 700;
    color: #fff;
}}
.badge-1 {{ background: var(--music-pink); }}
.badge-2 {{ background: var(--accent-orange); }}
.badge-3 {{ background: var(--accent); }}

.progress-bar-container {{
    position: relative;
    background: var(--bg);
    border-radius: 6px;
    height: 22px;
    margin-bottom: 0.75rem;
    overflow: hidden;
}}
.progress-bar {{
    height: 100%;
    background: linear-gradient(90deg, var(--accent-green), var(--accent));
    border-radius: 6px;
    transition: width 0.5s ease;
}}
.progress-label {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text);
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}}
.summary {{
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
}}
.todo-list {{
    list-style: none;
    padding: 0;
}}
.todo-list li {{
    font-size: 0.85rem;
    padding: 0.25rem 0;
    border-bottom: 1px solid var(--border);
    color: var(--text);
}}
.todo-list li::before {{
    content: "☐ ";
    color: var(--accent-orange);
}}

/* Script Section */
.script-section {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    margin-bottom: 2rem;
}}
.script-section h3 {{
    margin-bottom: 0.75rem;
    cursor: pointer;
}}
.script-section h3::after {{
    content: " ▸";
    font-size: 0.8rem;
}}
.script-section.open h3::after {{
    content: " ▾";
}}
.script-text {{
    display: none;
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--text-muted);
    background: var(--bg);
    padding: 1rem;
    border-radius: 8px;
    max-height: 400px;
    overflow-y: auto;
}}
.script-section.open .script-text {{
    display: block;
}}

/* All Projects Table */
.all-projects {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    margin-bottom: 2rem;
}}
.all-projects h3 {{
    margin-bottom: 0.75rem;
}}
.all-projects table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}}
.all-projects th, .all-projects td {{
    padding: 0.5rem 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}}
.all-projects th {{
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
}}
.all-projects tr:hover td {{
    background: rgba(88, 166, 255, 0.05);
}}

/* Status indicator */
.status-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 4px;
}}
.status-live {{ background: var(--accent-green); animation: pulse 2s infinite; }}
@keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
}}

footer {{
    text-align: center;
    color: var(--text-muted);
    font-size: 0.75rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
}}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>👁 Executive Audio Brief Portal</h1>
        <div class="subtitle">
            Cross-project status intelligence · ElevenLabs voice synthesis
        </div>
        <div class="timestamp">
            <span class="status-dot status-live"></span>
            Last generated: {html.escape(timestamp)}
        </div>
    </header>

    {audio_section}

    <div class="controls" id="controls">
        <label for="voiceSelect">Voice:</label>
        <select id="voiceSelect">
            {voice_options}
        </select>
        <button id="generateBtn" onclick="generateBrief()">
            🎙️ Generate Audio Brief
        </button>
        <button id="refreshBtn" onclick="refreshStatus()">
            🔄 Refresh Status
        </button>
    </div>
    <div id="serveHint" class="serve-hint" style="display:none;">
        ⚠️ Live generation requires server mode.
        Run: <code>python tools/executive_audio_brief.py --serve</code>
    </div>

    <h2 style="margin-bottom:1rem;">Top 3 Priorities</h2>
    <div class="cards-grid">
        {cards_html}
    </div>

    <div class="script-section" id="scriptSection" onclick="this.classList.toggle('open')">
        <h3>📝 Brief Script</h3>
        <div class="script-text">{script_escaped}</div>
    </div>

    <div class="all-projects">
        <h3>All Projects Overview</h3>
        <table>
            <thead>
                <tr>
                    <th>Project</th>
                    <th>Open</th>
                    <th>Done</th>
                    <th>Progress</th>
                    <th>In Brief</th>
                </tr>
            </thead>
            <tbody>
                {all_rows}
            </tbody>
        </table>
    </div>

    <footer>
        👁 AI-Manifest · Executive Audio Brief Portal · Powered by ElevenLabs<br>
        Tyler James Drake · Generated {html.escape(timestamp)}
    </footer>
</div>

<script>
// Detect static file:// mode — API endpoints only exist in --serve mode
const IS_STATIC = window.location.protocol === 'file:';
if (IS_STATIC) {{ document.getElementById('serveHint').style.display = 'block'; }}

function _showServeHint() {{
    document.getElementById('serveHint').style.display = 'block';
}}

async function generateBrief() {{
    if (IS_STATIC) {{ _showServeHint(); return; }}
    const btn = document.getElementById('generateBtn');
    const voiceId = document.getElementById('voiceSelect').value;
    btn.disabled = true;
    btn.textContent = '⏳ Generating...';
    try {{
        const resp = await fetch('/api/generate', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{ voice_id: voiceId }})
        }});
        if (resp.ok) {{
            window.location.reload();
        }} else {{
            const err = await resp.text();
            alert('Generation failed: ' + err);
        }}
    }} catch(e) {{
        alert('Request failed: ' + e.message);
    }} finally {{
        btn.disabled = false;
        btn.textContent = '🎙️ Generate Audio Brief';
    }}
}}

async function refreshStatus() {{
    if (IS_STATIC) {{ _showServeHint(); return; }}
    const btn = document.getElementById('refreshBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Refreshing...';
    try {{
        const resp = await fetch('/api/refresh', {{ method: 'POST' }});
        if (resp.ok) {{
            window.location.reload();
        }} else {{
            alert('Refresh failed');
        }}
    }} catch(e) {{
        alert('Request failed: ' + e.message);
    }} finally {{
        btn.disabled = false;
        btn.textContent = '🔄 Refresh Status';
    }}
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server with API endpoints
# ---------------------------------------------------------------------------

class BriefRequestHandler(SimpleHTTPRequestHandler):
    """Handler that serves the portal and handles API requests."""

    portal_state: dict = {}  # class-level shared state

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._serve_portal()
        elif self.path == "/api/status":
            self._serve_json(self.portal_state.get("all_statuses", []))
        elif self.path == "/api/voices":
            voices = list_available_voices()
            self._serve_json(voices)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/generate":
            self._handle_generate()
        elif self.path == "/api/refresh":
            self._handle_refresh()
        else:
            self.send_error(404)

    def _serve_portal(self) -> None:
        portal_html = self.portal_state.get("html", "<h1>Loading...</h1>")
        body = portal_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, data: Any) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_generate(self) -> None:
        """Generate a new audio brief with optional voice_id."""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            voice_id = body.get("voice_id")

            # Re-gather and regenerate
            result = build_brief(voice_id=voice_id, text_only=False)
            self.portal_state.update(result)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            msg = str(e).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(msg)

    def _handle_refresh(self) -> None:
        """Refresh status data without re-generating audio."""
        try:
            result = build_brief(text_only=True)
            # Keep existing audio if any
            existing_audio = self.portal_state.get("audio_path")
            result["audio_path"] = existing_audio

            # Regenerate HTML with existing audio
            voices = self.portal_state.get("voices", [])
            result["html"] = generate_portal_html(
                result["top3"],
                result["script"],
                existing_audio,
                voices,
                result["all_statuses"],
                result["timestamp"],
            )
            self.portal_state.update(result)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            msg = str(e).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, format: str, *args) -> None:
        """Quieter logging."""
        print(f"[PORTAL] {args[0]}" if args else "")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def build_brief(
    voice_id: str | None = None,
    text_only: bool = False,
) -> dict[str, Any]:
    """Build a complete brief — gather, rank, script, synthesize, render HTML."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Gather
    all_statuses = gather_all_statuses()
    print(f"Gathered status from {len(all_statuses)} projects")

    # 2. Rank
    top3 = rank_projects(all_statuses)
    print(f"Top 3: {', '.join(p['sigil'] + p['name'] for p in top3)}")

    # 3. Script
    script = generate_brief_script(top3, timestamp)
    print(f"Brief script: {len(script)} chars")

    # 4. Voices — always fetch so the dropdown is populated in static-file mode.
    # Synthesis is skipped in text_only mode but voices are embedded in the HTML either way.
    voices: list[dict] = list_available_voices()

    # 5. Synthesize (unless text-only)
    audio_path = None
    if not text_only:
        try:
            audio_path = synthesize_brief(script, voice_id=voice_id)
            print(f"Audio saved: {audio_path}")
        except Exception as e:
            print(f"TTS failed (continuing without audio): {e}", file=sys.stderr)

    # 5. Render HTML
    portal_html = generate_portal_html(
        top3, script, audio_path, voices, all_statuses, timestamp
    )

    # 6. Save HTML
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(portal_html, encoding="utf-8")
    print(f"Portal HTML: {REPORT_PATH}")

    return {
        "top3": top3,
        "script": script,
        "audio_path": audio_path,
        "voices": voices,
        "all_statuses": all_statuses,
        "html": portal_html,
        "timestamp": timestamp,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Executive Audio Brief Portal")
    parser.add_argument("--serve", action="store_true", help="Launch interactive portal server")
    parser.add_argument("--port", type=int, default=8200, help="Server port (default: 8200)")
    parser.add_argument("--text-only", action="store_true", help="Generate script only, skip TTS")
    parser.add_argument("--voice-id", type=str, default=None, help="ElevenLabs voice ID")
    args = parser.parse_args()

    print("=" * 60)
    print("👁 Executive Audio Brief Portal")
    print("=" * 60)

    result = build_brief(voice_id=args.voice_id, text_only=args.text_only)

    if args.text_only:
        print("\n--- BRIEF SCRIPT ---")
        print(result["script"])
        print("--- END ---\n")

    if args.serve:
        BriefRequestHandler.portal_state = result
        server = HTTPServer(("127.0.0.1", args.port), BriefRequestHandler)
        url = f"http://127.0.0.1:{args.port}"
        print(f"\n🌐 Portal live at {url}")
        print("Press Ctrl+C to stop.\n")

        # Auto-open in browser
        import webbrowser
        webbrowser.open(url)

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down portal.")
            server.server_close()
    else:
        print(f"\nDone. Open {REPORT_PATH} in a browser.")
        if not args.text_only:
            import webbrowser
            webbrowser.open(str(REPORT_PATH))


if __name__ == "__main__":
    main()
