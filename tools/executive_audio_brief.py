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
from socketserver import ThreadingMixIn
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
    sys.path.append(str(_WORKSPACE_ROOT))

# Add project root to path for any remaining project-local imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.integrations.elevenlabs import ElevenLabsClient
from src.config.elevenlabs_settings import DEFAULT_MODEL_ID
from src.utils.lily_portrait import get_portrait_img_tag
from src.utils.roadmap_panel import (
    load_roadmap_data,
    render_roadmap_tab_html,
    render_tab_nav_html,
    ROADMAP_STYLES,
    TAB_NAV_SCRIPT,
)
from src.utils.todos_db import (
    init_db, get_open_todos, get_done_todos, mark_done, get_todo_by_id,
    add_todo, update_priority, get_open_todos_by_autonomy,
)
from src.utils.priority_scorer import score_priority

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
        "sigil": "Σ",
        "name": "Capital",
        "key": "capital",
        "root": WORKSPACE_ROOT / "ΣCapital",
        "always_include": False,
        "priority_weight": 4,
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


def gather_project_status(project: dict) -> dict[str, Any]:
    """Gather status for a single project from the todos DB."""
    root = project["root"]
    key = project["key"]
    status: dict[str, Any] = {
        "sigil": project["sigil"],
        "name": project["name"],
        "key": key,
        "exists": root.exists(),
        "always_include": project["always_include"],
        "priority_weight": project["priority_weight"],
        # Each entry: {"id": int, "text": str}
        "ai_todos": [],
        "tyler_todos": [],
        "scan_todos": [],
        "full_todos": [],
        "supervised_todos": [],
        "human_todos": [],
        "profile": {},
        "summary": "",
        "active_tasks": 0,
        "completed_tasks": 0,
    }

    open_rows = get_open_todos(key)
    done_count = len(get_done_todos(key))

    status["ai_todos"] = []
    status["tyler_todos"] = []
    status["scan_todos"] = []

    status["full_todos"] = sorted(
        [{"id": r["id"], "text": r["text"], "priority": r.get("priority", 5), "source": r["source"]}
         for r in open_rows if r.get("autonomy_level") == "full"],
        key=lambda t: t["priority"], reverse=True,
    )
    status["supervised_todos"] = sorted(
        [{"id": r["id"], "text": r["text"], "priority": r.get("priority", 5), "source": r["source"]}
         for r in open_rows if r.get("autonomy_level") == "supervised"],
        key=lambda t: t["priority"], reverse=True,
    )
    status["human_todos"] = sorted(
        [{"id": r["id"], "text": r["text"], "priority": r.get("priority", 5), "source": r["source"]}
         for r in open_rows if r.get("autonomy_level") == "human" or r.get("autonomy_level") is None],
        key=lambda t: t["priority"], reverse=True,
    )
    status["active_tasks"] = len(open_rows)
    status["completed_tasks"] = done_count

    if root.exists():
        for profile_name in ["PROJECT_PROFILE.json", "ARTIST_PROFILE.json", "SUBJECT_PROFILE.json"]:
            profile_path = root / profile_name
            if profile_path.exists():
                status["profile"] = _read_json_safe(profile_path)
                break
    else:
        status["summary"] = f"{project['sigil']}{project['name']}: Project directory not found."
        return status

    total = status["active_tasks"] + status["completed_tasks"]
    pct = round(100 * status["completed_tasks"] / total) if total > 0 else 0
    top_texts = (
        [t["text"] for t in status["full_todos"][:2]]
        + [t["text"] for t in status["supervised_todos"][:2]]
        + [t["text"] for t in status["human_todos"][:1]]
    )
    summary_lines = [
        f"{project['sigil']}{project['name']}: {status['active_tasks']} open tasks, "
        f"{status['completed_tasks']} completed ({pct}% done)."
    ]
    if top_texts:
        summary_lines.append("Top priorities: " + "; ".join(top_texts[:3]) + ".")
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

def generate_brief_script(all_statuses: list[dict], timestamp: str) -> str:
    """Generate the spoken executive brief text covering all 5 projects."""
    lines = [
        f"Executive Project Brief — {timestamp}.",
        "",
        "Good day, Tyler. Here's your priority status update.",
        "",
    ]

    ranked = sorted(all_statuses, key=lambda s: s.get("score", 0), reverse=True)
    for i, proj in enumerate(ranked, 1):
        if i <= 3:
            lines.append(f"Priority {i}: {proj['sigil']} {proj['name']}.")
        else:
            lines.append(f"Also active: {proj['sigil']} {proj['name']}.")
        lines.append(proj["summary"])
        if proj.get("full_todos"):
            top_offload = proj["full_todos"][0]["text"]
            lines.append(f"Fully offloadable: {top_offload}")
        lines.append("")

    # Closing
    total_open = sum(p["active_tasks"] for p in all_statuses)
    lines.append(
        f"Across all projects, you have {total_open} open tasks. "
        "Focus on the highest-impact items first. End of brief."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audio synthesis
# ---------------------------------------------------------------------------

def synthesize_brief(
    script: str,
    output_path: Path | None = None,
) -> Path:
    """Synthesize the brief script to an MP3 file via ElevenLabs (Lily voice, hard-locked)."""
    client = ElevenLabsClient()

    # Hard-lock to Lily — raise clearly if not found
    voices = client.list_voices()
    lily_voice = next((v for v in voices if "lily" in v["name"].lower()), None)
    if not lily_voice:
        raise RuntimeError(
            "Lily voice not found in ElevenLabs account. "
            "Cannot generate executive brief without Lily. "
            "Check your ElevenLabs account or add the Lily voice."
        )
    voice_id = lily_voice["voice_id"]

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

def _priority_badge(priority: int) -> str:
    """Return an inline priority badge HTML span."""
    if priority >= 8:
        cls = "p-high"
    elif priority >= 5:
        cls = "p-mid"
    else:
        cls = "p-low"
    return f'<span class="priority-badge-inline {cls}">P{priority}</span>'


def _status_card_html(proj: dict, rank: int) -> str:
    """Generate an HTML card for a project status."""
    sigil = html.escape(proj["sigil"])
    name = html.escape(proj["name"])
    summary = html.escape(proj["summary"])
    active = proj["active_tasks"]
    done = proj["completed_tasks"]
    total = active + done
    pct = round(100 * done / total) if total > 0 else 0

    full_count = len(proj.get("full_todos", []))
    supervised_count = len(proj.get("supervised_todos", []))
    human_count = len(proj.get("human_todos", []))

    def _todo_rows(todos: list, limit: int = 5) -> str:
        return "".join(
            f'<li>'
            f'{_priority_badge(t.get("priority", 5))}'
            f'<span class="todo-text">{html.escape(t["text"])}</span>'
            f'<span class="source-tag">{html.escape(t.get("source", ""))}</span>'
            f'<button class="done-btn" onclick="markDone({t["id"]}, this)" title="Mark done">✓</button>'
            f'</li>'
            for t in todos[:limit]
        )

    # 'full' todos are shown exclusively in the top ⚡ Fully Offloadable panel;
    # omit them from per-project cards to avoid duplicate entries.
    full_html = ""

    supervised_html = ""
    if proj.get("supervised_todos"):
        supervised_html = f"""<div class="todo-section">
            <div class="todo-label supervised-label">👁 Supervised \u2014 AI Executes, You Verify ({supervised_count})</div>
            <ul class="todo-list">{_todo_rows(proj["supervised_todos"])}</ul>
        </div>"""

    human_html = ""
    if proj.get("human_todos"):
        human_html = f"""<div class="todo-section">
            <div class="todo-label human-label">👤 Human \u2014 Needs Tyler ({human_count})</div>
            <ul class="todo-list">{_todo_rows(proj["human_todos"])}</ul>
        </div>"""

    add_todo_form_html = f"""<div class="add-todo-form">
  <input type="text" class="add-todo-input" placeholder="Add a todo\u2026" data-project="{html.escape(proj['key'])}" />
  <input type="number" class="add-todo-priority" min="1" max="10" placeholder="Priority (1-10)" />
  <button class="add-todo-btn" onclick="addTodo(this)">\uff0b</button>
  <span class="priority-hint">leave blank \u2192 AI scores</span>
</div>"""

    if rank == 1:
        badge_class = "badge-1"
    elif rank == 2:
        badge_class = "badge-2"
    elif rank == 3:
        badge_class = "badge-3"
    else:
        badge_class = "badge-secondary"

    card_extra_class = " rank-secondary" if rank > 3 else ""

    return f"""
    <div class="status-card{card_extra_class}">
        <div class="card-header">
            <span class="priority-badge {badge_class}">#{rank}</span>
            <span class="project-sigil">{sigil}</span>
            <h3>{name}</h3>
        </div>
        <div class="progress-bar-container" data-open="{active}" data-total="{total}">
            <div class="progress-bar" style="width: {pct}%"></div>
            <span class="progress-label">{done}/{total} tasks ({pct}%)</span>
        </div>
        <p class="summary">{summary}</p>
        {full_html}
        {supervised_html}
        {human_html}
        {add_todo_form_html}
    </div>
    """


def _offload_panel_html(all_statuses: list[dict]) -> str:
    """Generate the cross-project ⚡ Fully Offloadable panel."""
    rows: list[dict] = []
    for s in all_statuses:
        project_label = f"{html.escape(s['sigil'])}{html.escape(s['name'])}"
        for t in s.get("full_todos", []):
            rows.append({
                "priority": t.get("priority", 5),
                "project": project_label,
                "id": t["id"],
                "text": t["text"],
                "source": t.get("source", ""),
            })
    rows.sort(key=lambda r: r["priority"], reverse=True)

    if not rows:
        return """<div class="offload-panel">
  <h2>⚡ Fully Offloadable</h2>
  <p class="offload-subtitle">These AI tasks require zero Tyler involvement — delegate freely.</p>
  <p style="color:var(--text-muted);font-style:italic;">No fully offloadable tasks yet.</p>
</div>"""

    table_rows = "".join(
        f"<tr>"
        f"<td>{_priority_badge(r['priority'])}</td>"
        f"<td>{r['project']}</td>"
        f"<td><span class='todo-text'>{html.escape(r['text'])}</span>"
        f" <span class='source-tag'>{html.escape(r['source'])}</span></td>"
        f"<td><button class='done-btn' onclick=\"markDone({r['id']}, this)\" title='Mark done'>✓</button></td>"
        f"</tr>"
        for r in rows
    )
    return f"""<div class="offload-panel">
  <h2>⚡ Fully Offloadable</h2>
  <p class="offload-subtitle">These AI tasks require zero Tyler involvement — delegate freely.</p>
  <table class="offload-table">
    <thead><tr><th>Pri</th><th>Project</th><th>Task</th><th></th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>"""


def generate_portal_html(
    all_statuses: list[dict],
    script: str,
    audio_path: Path | None,
    voices: list[dict],
    timestamp: str,
) -> str:
    """Generate the full interactive portal HTML covering all 5 projects."""
    all_ranked = sorted(all_statuses, key=lambda s: s.get("score", 0), reverse=True)
    cards_html = "\n".join(
        _status_card_html(p, i) for i, p in enumerate(all_ranked, 1)
    )
    top3_keys = {s["key"] for s in all_ranked[:3]}
    offload_panel = _offload_panel_html(all_statuses)
    tab_nav_html = render_tab_nav_html()
    roadmap_tab_html = render_roadmap_tab_html(load_roadmap_data())

    # Lily portrait — injected as inline data-URI img tag
    # <!-- LILY_PORTRAIT --> marks the injection point in the rendered HTML
    lily_img_tag = get_portrait_img_tag(max_width=140)

    # Voice selector options — Lily is default
    _lily_id = next((v["voice_id"] for v in voices if "lily" in v["name"].lower()), None)
    voice_options = "\n".join(
        f'<option value="{html.escape(v["voice_id"])}"{" selected" if v["voice_id"] == _lily_id else ""}>{html.escape(v["name"])}</option>'
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
        in_brief = "✅" if s["key"] in top3_keys else ""
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
    --bg: #080c14;
    --surface: rgba(22, 28, 40, 0.7);
    --surface-solid: #161c28;
    --border: rgba(99, 130, 200, 0.18);
    --border-glow: rgba(88, 166, 255, 0.35);
    --text: #e8eef8;
    --text-muted: #7a8aa0;
    --accent: #58a6ff;
    --accent-green: #3fb950;
    --accent-orange: #d29922;
    --accent-red: #f85149;
    --accent-purple: #bc8cff;
    --music-pink: #ff6b9d;
    --radius: 16px;
    --blur: 18px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
    background-image:
        radial-gradient(ellipse at 20% 20%, rgba(88, 166, 255, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 80%, rgba(188, 140, 255, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 50%, rgba(63, 185, 80, 0.04) 0%, transparent 60%);
    background-attachment: fixed;
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
.lily-portrait {{
    position: relative;
    display: inline-block;
    margin-bottom: 1rem;
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
    backdrop-filter: blur(var(--blur));
    -webkit-backdrop-filter: blur(var(--blur));
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    transition: border-color 0.3s, box-shadow 0.3s, transform 0.2s;
}}
.status-card:hover {{
    border-color: var(--border-glow);
    box-shadow: 0 0 24px rgba(88, 166, 255, 0.12), 0 8px 32px rgba(0,0,0,0.4);
    transform: translateY(-2px);
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
.badge-secondary {{ background: rgba(139,148,158,0.35); }}
.rank-secondary {{ opacity: 0.72; border-color: var(--border); }}

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
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
}}
.todo-list li::before {{
    content: "☐ ";
    color: var(--accent-orange);
    flex-shrink: 0;
}}
.todo-text {{
    flex: 1;
}}
.done-btn {{
    flex-shrink: 0;
    background: none;
    border: 1px solid var(--border);
    color: var(--accent-green);
    border-radius: 4px;
    padding: 0.05rem 0.35rem;
    font-size: 0.75rem;
    cursor: pointer;
    opacity: 0.6;
    transition: opacity 0.15s, background 0.15s;
}}
.done-btn:hover {{
    opacity: 1;
    background: rgba(63, 185, 80, 0.15);
}}
.done-btn:disabled {{
    opacity: 0.3;
    cursor: wait;
}}
.todo-section {{
    margin-top: 0.5rem;
}}
.todo-label {{
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    margin-bottom: 0.3rem;
    display: inline-block;
}}
.ai-label {{
    background: rgba(88, 166, 255, 0.15);
    color: var(--accent);
}}
.tyler-label {{
    background: rgba(63, 185, 80, 0.15);
    color: var(--accent-green);
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

/* ── Add-Todo Form ───────────────────────────────────────────── */
.add-todo-form {{
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-top: 0.75rem;
    flex-wrap: wrap;
}}
.add-todo-input {{
    flex: 1;
    min-width: 0;
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: 0.35rem 0.6rem;
    font-size: 0.82rem;
}}
.add-todo-input:focus {{
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 8px rgba(88,166,255,0.2);
}}
.add-todo-priority {{
    width: 80px;
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: 0.35rem 0.6rem;
    font-size: 0.82rem;
    -moz-appearance: textfield;
}}
.add-todo-btn {{
    background: linear-gradient(135deg, var(--accent), var(--accent-purple));
    border: none;
    border-radius: 8px;
    color: #fff;
    font-size: 1rem;
    padding: 0.3rem 0.7rem;
    cursor: pointer;
    font-weight: 700;
    transition: opacity 0.2s;
}}
.add-todo-btn:hover {{ opacity: 0.85; }}
.priority-hint {{ font-size: 0.72rem; color: var(--text-muted); }}
.priority-badge-inline {{
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.1rem 0.35rem;
    border-radius: 4px;
    flex-shrink: 0;
}}
.p-high {{ background: rgba(248,81,73,0.25); color: #f85149; }}
.p-mid  {{ background: rgba(210,153,34,0.25); color: #d29922; }}
.p-low  {{ background: rgba(139,148,158,0.2); color: #8b949e; }}

/* ── Lily Prompt Modal ───────────────────────────────────────── */
.lily-edit-btn {{    position: absolute;
    top: 4px;
    right: 4px;
    background: rgba(0,0,0,0.55);
    border: none;
    border-radius: 50%;
    width: 22px;
    height: 22px;
    padding: 0;
    cursor: pointer;
    opacity: 0.35;
    transition: opacity 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    color: #fff;
}}
.lily-edit-btn:hover {{ opacity: 0.9; }}

.modal-overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.72);
    z-index: 9000;
    align-items: center;
    justify-content: center;
}}
.modal-overlay.open {{ display: flex; }}

.modal-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.75rem;
    width: min(640px, 94vw);
    max-height: 90vh;
    overflow-y: auto;
    position: relative;
    box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}}
.modal-card h2 {{
    font-size: 1.15rem;
    margin-bottom: 1rem;
    background: linear-gradient(135deg, var(--accent), var(--accent-purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}
.modal-close {{
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 1.3rem;
    cursor: pointer;
    line-height: 1;
}}
.modal-close:hover {{ color: var(--text); }}
.modal-label {{
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
    display: block;
}}
#lily-positive-prompt {{
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 0.85rem;
    padding: 0.75rem;
    resize: vertical;
    font-family: inherit;
    margin-bottom: 1rem;
}}
#lily-positive-prompt:focus {{
    outline: none;
    border-color: var(--accent);
}}
.modal-actions {{
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
}}
.modal-actions button {{
    padding: 0.5rem 1.1rem;
    border-radius: 8px;
    border: none;
    font-size: 0.88rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s;
}}
.modal-actions button:disabled {{ opacity: 0.5; cursor: wait; }}
.btn-save {{
    background: linear-gradient(135deg, var(--accent), var(--accent-purple));
    color: #fff;
}}
.btn-regen {{
    background: linear-gradient(135deg, var(--accent-green), #2ea043);
    color: #fff;
}}
.btn-cancel {{
    background: var(--bg);
    border: 1px solid var(--border) !important;
    color: var(--text-muted);
}}
.modal-status {{
    font-size: 0.8rem;
    margin-top: 0.5rem;
    color: var(--text-muted);
    min-height: 1.2em;
}}

/* ── Autonomy Labels ─────────────────────────────────────────── */
.full-label {{
    background: rgba(210, 153, 34, 0.2);
    color: #d29922;
    border: 1px solid rgba(210,153,34,0.3);
}}
.supervised-label {{
    background: rgba(88, 166, 255, 0.15);
    color: var(--accent);
}}
.human-label {{
    background: rgba(63, 185, 80, 0.15);
    color: var(--accent-green);
}}
.source-tag {{
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.08rem 0.28rem;
    border-radius: 3px;
    background: rgba(139,148,158,0.15);
    color: var(--text-muted);
    flex-shrink: 0;
    letter-spacing: 0.03em;
}}

/* ── Offload Panel ───────────────────────────────────────────── */
.offload-panel {{
    background: var(--surface);
    border: 1px solid rgba(210,153,34,0.45);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin-bottom: 2rem;
    box-shadow: 0 0 20px rgba(210,153,34,0.08);
}}
.offload-panel h2 {{
    font-size: 1.15rem;
    color: #d29922;
    margin-bottom: 0.3rem;
}}
.offload-subtitle {{
    color: var(--text-muted);
    font-size: 0.88rem;
    margin-bottom: 1rem;
}}
.offload-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.87rem;
}}
.offload-table th, .offload-table td {{
    padding: 0.45rem 0.65rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}}
.offload-table th {{
    color: var(--text-muted);
    font-size: 0.78rem;
    text-transform: uppercase;
    font-weight: 600;
}}
.offload-table tr:hover td {{
    background: rgba(210,153,34,0.05);
}}

{ROADMAP_STYLES}

</style>
</head>
<body>
<!-- Lily Prompt Modal -->
<div class="modal-overlay" id="lily-prompt-modal" onclick="lilyModalClickOutside(event)">
  <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="lily-modal-title">
    <button class="modal-close" onclick="closeLilyModal()" aria-label="Close">&times;</button>
    <h2 id="lily-modal-title">Edit Lily&rsquo;s Portrait Prompt</h2>
    <label class="modal-label" for="lily-positive-prompt">Positive Prompt</label>
    <textarea id="lily-positive-prompt" rows="10" spellcheck="false"></textarea>
    <div class="modal-actions">
      <button class="btn-save" id="lily-save-btn" onclick="lilyModalSave()">Save & Regenerate</button>
      <button class="btn-cancel" onclick="closeLilyModal()">Cancel</button>
    </div>
    <div class="modal-status" id="lily-modal-status"></div>
  </div>
</div>
<div class="container">
    <header>
        <!-- LILY_PORTRAIT -->
        <div class="lily-portrait" style="position:relative;display:inline-block;">
            {lily_img_tag}
            <button class="lily-edit-btn" onclick="openLilyModal()" title="Edit Lily's portrait prompt"
              onmouseenter="this.style.opacity='0.9'" onmouseleave="this.style.opacity='0.35'">✏</button>
        </div>
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
            🔄 Regenerate
        </button>
        <button id="refreshBtn" onclick="refreshStatus()">
            🔄 Refresh Status
        </button>
    </div>
    <div id="serveHint" class="serve-hint" style="display:none;">
        ⚠️ Live generation requires server mode.
        Run: <code>python tools/executive_audio_brief.py --serve</code>
    </div>

    {tab_nav_html}

    <div id="tab-overview" class="tab-panel active">

    {offload_panel}

    <h2 style="margin-bottom:1rem;">Project Priorities</h2>
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

    </div>

    <div id="tab-roadmap" class="tab-panel">
        {roadmap_tab_html}
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
        btn.textContent = '🔄 Regenerate';
    }}
}}

function _inlineMsg(li, text, color) {{
    if (!li) return;
    const span = document.createElement('span');
    span.textContent = text;
    span.style.cssText = 'color:' + color + ';font-size:0.75rem;margin-left:0.4rem;';
    li.appendChild(span);
}}

function _updateProgressBar(card) {{
    if (!card) return;
    const pbc = card.querySelector('.progress-bar-container');
    if (!pbc) return;
    let open = parseInt(pbc.dataset.open || '0', 10);
    const total = parseInt(pbc.dataset.total || '0', 10);
    if (open > 0) open -= 1;
    pbc.dataset.open = String(open);
    const done = total - open;
    const pct = total > 0 ? Math.round(100 * done / total) : 0;
    const bar = pbc.querySelector('.progress-bar');
    const label = pbc.querySelector('.progress-label');
    if (bar) bar.style.width = pct + '%';
    if (label) label.textContent = done + '/' + total + ' tasks (' + pct + '%)';
}}

async function markDone(todoId, btnEl) {{
    if (IS_STATIC) {{ _showServeHint(); return; }}
    btnEl.disabled = true;
    try {{
        const resp = await fetch('/api/todo/done', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{id: todoId}})
        }});
        const row = btnEl.closest('li') || btnEl.closest('tr');
        const card = row ? row.closest('.status-card') : null;
        if (resp.ok) {{
            if (row) {{
                row.style.transition = 'opacity 0.3s';
                row.style.opacity = '0';
                setTimeout(() => {{
                    row.remove();
                    _updateProgressBar(card);
                }}, 300);
            }}
        }} else if (resp.status === 409) {{
            btnEl.style.display = 'none';
            _inlineMsg(row, 'Already done', 'var(--accent-green)');
        }} else {{
            btnEl.style.display = 'none';
            _inlineMsg(row, 'Not found', 'var(--text-muted)');
        }}
    }} catch(e) {{
        btnEl.disabled = false;
        const row = btnEl.closest('li') || btnEl.closest('tr');
        _inlineMsg(row, 'Error: ' + e.message, 'var(--accent-red)');
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

async function addTodo(btn) {{
    const row = btn.closest('.add-todo-form');
    const project = row.querySelector('.add-todo-input').dataset.project;
    const text = row.querySelector('.add-todo-input').value.trim();
    const priorityInput = row.querySelector('.add-todo-priority').value;
    const priority = priorityInput ? parseInt(priorityInput) : null;
    if (!text) return;
    btn.disabled = true;
    const res = await fetch('/api/todos/add', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{project, text, priority}})
    }});
    const data = await res.json();
    if (data.ok) {{
        location.reload();
    }}
    btn.disabled = false;
}}

// ── Lily Prompt Modal ────────────────────────────────────────────────────
function openLilyModal() {{
    if (IS_STATIC) {{ _showServeHint(); return; }}
    const modal = document.getElementById('lily-prompt-modal');
    const ta = document.getElementById('lily-positive-prompt');
    const status = document.getElementById('lily-modal-status');
    status.textContent = 'Loading current prompt…';
    ta.value = '';
    modal.classList.add('open');
    fetch('/lily/prompt')
        .then(r => r.json())
        .then(data => {{
            ta.value = data.positive_prompt || '';
            status.textContent = '';
        }})
        .catch(e => {{
            status.textContent = 'Failed to load prompt: ' + e.message;
        }});
}}

function closeLilyModal() {{
    document.getElementById('lily-prompt-modal').classList.remove('open');
    document.getElementById('lily-modal-status').textContent = '';
}}

function lilyModalClickOutside(e) {{
    if (e.target === document.getElementById('lily-prompt-modal')) closeLilyModal();
}}

async function lilyModalSave() {{
    if (IS_STATIC) {{ _showServeHint(); return; }}
    const btn = document.getElementById('lily-save-btn');
    const status = document.getElementById('lily-modal-status');
    const prompt = document.getElementById('lily-positive-prompt').value.trim();
    if (!prompt) {{ status.textContent = 'Prompt cannot be empty.'; return; }}

    btn.disabled = true;
    btn.textContent = 'Saving…';
    status.textContent = '';

    try {{
        // 1. Save prompt
        const saveResp = await fetch('/lily/prompt', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{positive_prompt: prompt}})
        }});
        if (!saveResp.ok) {{
            status.textContent = 'Save failed (' + saveResp.status + ').';
            return;
        }}

        // 2. Regenerate portrait
        btn.textContent = 'Regenerating…';
        const regenResp = await fetch('/lily/portrait/regen');
        if (regenResp.ok) {{
            status.textContent = '✅ Portrait regenerated. Reloading…';
            setTimeout(() => {{ closeLilyModal(); window.location.reload(); }}, 1200);
        }} else {{
            status.textContent = 'Regen failed (' + regenResp.status + '). Prompt was saved.';
        }}
    }} catch(e) {{
        status.textContent = 'Error: ' + e.message;
    }} finally {{
        btn.disabled = false;
        btn.textContent = 'Save & Regenerate';
    }}
}}

// Auto-refresh every 60s — skip the tick when audio is actively playing
(function() {{
    var REFRESH_INTERVAL = 60000;
    setInterval(function() {{
        var audio = document.getElementById('briefAudio');
        var playing = audio && !audio.paused && !audio.ended && audio.readyState > 2;
        if (!playing) {{
            window.location.reload();
        }}
    }}, REFRESH_INTERVAL);
}})();

{TAB_NAV_SCRIPT}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server with API endpoints
# ---------------------------------------------------------------------------

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer that handles each request in a new thread, preventing blocking."""
    daemon_threads = True


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
        elif self.path == "/lily/prompt":
            self._handle_lily_get_prompt()
        elif self.path == "/lily/portrait/regen":
            self._handle_lily_regen()
        elif self.path == "/health":
            self._serve_json({"ok": True, "port": self.server.server_address[1]})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/generate":
            self._handle_generate()
        elif self.path == "/api/refresh":
            self._handle_refresh()
        elif self.path == "/api/todo/done":
            self._handle_todo_done()
        elif self.path == "/api/todos/add":
            self._handle_todos_add()
        elif self.path == "/api/todos/priority":
            self._handle_todos_priority()
        elif self.path == "/lily/prompt":
            self._handle_lily_post_prompt()
        else:
            self.send_error(404)

    def _build_fresh_portal_html(self) -> str:
        """Regenerate portal HTML from live DB state (no TTS / voice API calls)."""
        init_db()
        from tools.migrate_todos import auto_migrate_if_needed
        auto_migrate_if_needed()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        all_statuses = gather_all_statuses()
        top3 = rank_projects(all_statuses)
        script = generate_brief_script(all_statuses, timestamp)
        existing_audio = self.portal_state.get("audio_path")
        voices = self.portal_state.get("voices", [])
        return generate_portal_html(all_statuses, script, existing_audio, voices, timestamp)

    def _serve_portal(self) -> None:
        portal_html = self._build_fresh_portal_html()
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
        """Generate a new audio brief (always uses Lily voice)."""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            # Body accepted but voice_id ignored — Lily is hard-locked
            if content_len > 0:
                self.rfile.read(content_len)

            # Re-gather and regenerate
            result = build_brief(text_only=False)
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
                result["all_statuses"],
                result["script"],
                existing_audio,
                voices,
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

    def _handle_todo_done(self) -> None:
        """Mark a single todo as done."""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            todo_id = int(body["id"])

            todo = get_todo_by_id(todo_id)
            if todo is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "todo not found"}')
                return

            if todo["done"] == 1:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "already done"}')
                return

            success = mark_done(todo_id)
            if success:
                self._serve_json({"ok": True})
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "not found or already done"}')
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

    def _handle_todos_add(self) -> None:
        """POST /api/todos/add — add a new todo with optional AI priority scoring."""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            project: str = body["project"]
            text: str = body["text"]
            priority_raw = body.get("priority")
            if priority_raw is None:
                from src.utils.todos_db import get_open_todos
                existing = get_open_todos(project)
                priority = score_priority(text, project, existing_todos=existing)
            else:
                priority = int(priority_raw)
            new_id = add_todo(project, text, priority, source="TYLER")
            self._serve_json({"ok": True, "id": new_id, "priority": priority})
        except (KeyError, ValueError) as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    def _handle_todos_priority(self) -> None:
        """POST /api/todos/priority — update priority on an existing todo."""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            todo_id = int(body["id"])
            priority = int(body["priority"])
            update_priority(todo_id, priority)
            self._serve_json({"ok": True})
        except (KeyError, ValueError) as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    def _handle_lily_get_prompt(self) -> None:
        """GET /lily/prompt → JSON {"positive_prompt": "..."}"""
        try:
            from src.utils.lily_config_db import get_active_prompt
            positive, _negative = get_active_prompt()
            self._serve_json({"positive_prompt": positive})
        except Exception as e:
            msg = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def _handle_lily_post_prompt(self) -> None:
        """POST /lily/prompt → update DB active prompt → 200 OK"""
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            positive_prompt: str = body.get("positive_prompt", "").strip()
            if not positive_prompt:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "positive_prompt is required"}')
                return
            from src.utils.lily_config_db import update_active_prompt
            update_active_prompt(positive_prompt)
            self._serve_json({"ok": True})
        except Exception as e:
            msg = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def _handle_lily_regen(self) -> None:
        """GET /lily/portrait/regen → delete today's cache + regenerate → JSON status"""
        try:
            from src.utils.lily_portrait import (
                _today_cache_path,
                _IMAGE_CACHE_DIR,
                get_daily_portrait,
            )
            # Delete today's cached portrait so get_daily_portrait regenerates
            today_path = _today_cache_path()
            if today_path.exists():
                today_path.unlink()
            # Also delete today's SVG fallback if present
            from datetime import date
            today = date.today().isoformat()
            svg_path = _IMAGE_CACHE_DIR / f"lily_portrait_{today}.svg"
            if svg_path.exists():
                svg_path.unlink()
            # Regenerate
            new_path = get_daily_portrait()
            self._serve_json({"status": "ok", "path": str(new_path)})
        except Exception as e:
            msg = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, format: str, *args) -> None:
        """Quieter logging."""
        print(f"[PORTAL] {args[0]}" if args else "")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def build_brief(
    text_only: bool = False,
) -> dict[str, Any]:
    """Build a complete brief — gather, rank, script, synthesize, render HTML."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 0. Ensure DB ready; auto-migrate flat files on first run
    init_db()
    from tools.migrate_todos import auto_migrate_if_needed
    auto_migrate_if_needed()

    # 1. Gather
    all_statuses = gather_all_statuses()
    print(f"Gathered status from {len(all_statuses)} projects")

    # 2. Rank
    top3 = rank_projects(all_statuses)
    print(f"Top 3: {', '.join(p['sigil'] + p['name'] for p in top3)}")

    # 3. Script
    script = generate_brief_script(all_statuses, timestamp)
    print(f"Brief script: {len(script)} chars")

    # 4. Voices — always fetch so the dropdown is populated in static-file mode.
    # Synthesis is skipped in text_only mode but voices are embedded in the HTML either way.
    voices: list[dict] = list_available_voices()

    # 5. Synthesize (unless text-only)
    audio_path = None
    if not text_only:
        try:
            audio_path = synthesize_brief(script)
            print(f"Audio saved: {audio_path}")
        except Exception as e:
            print(f"TTS failed (continuing without audio): {e}", file=sys.stderr)

    # 5. Render HTML
    portal_html = generate_portal_html(
        all_statuses, script, audio_path, voices, timestamp
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
    args = parser.parse_args()

    print("=" * 60)
    print("👁 Executive Audio Brief Portal")
    print("=" * 60)

    if args.serve:
        # Bind port BEFORE build_brief() so the portal launcher's
        # Wait-PortListening (15 s) never times out due to slow ElevenLabs API
        # calls. Initial state is built in a background thread; _serve_portal()
        # always rebuilds HTML from live DB so there is no stale-data window.
        import threading
        import webbrowser
        BriefRequestHandler.portal_state = {}
        server = ThreadedHTTPServer(("127.0.0.1", args.port), BriefRequestHandler)
        url = f"http://127.0.0.1:{args.port}"
        print(f"\n🌐 Portal live at {url}")
        print("Press Ctrl+C to stop.\n")
        webbrowser.open(url)

        def _init_state() -> None:
            try:
                r = build_brief(text_only=args.text_only)
                BriefRequestHandler.portal_state = r
            except Exception as exc:
                print(f"Background brief build failed: {exc}", file=sys.stderr)

        threading.Thread(target=_init_state, daemon=True).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down portal.")
            server.server_close()
    else:
        result = build_brief(text_only=args.text_only)
        if args.text_only:
            print("\n--- BRIEF SCRIPT ---")
            print(result["script"])
            print("--- END ---\n")
        else:
            print(f"\nDone. Open {REPORT_PATH} in a browser.")
            import webbrowser
            webbrowser.open(str(REPORT_PATH))


if __name__ == "__main__":
    main()
