"""Roadmap panel — renders the cross-project FR roadmap tab for the executive
brief portal (executive_brief_portal.html).

Consumes the structured JSON roadmap artifact produced by the companion
⊕Workspace FR (FR-20260630-cross-project-roadmap-generator). Reconciles
against whatever schema that side actually ships; see SCHEMA ASSUMPTION below.

SCHEMA ASSUMPTION (documented for reconciliation with ⊕Workspace):
    {
        "generated_at": "2026-06-30T00:00:00Z",
        "nodes": [
            {
                "id": "FR-20260630-cross-project-roadmap-generator",
                "title": "P8 Cross-Project Roadmap Generator",
                "project": "\u2295Workspace",
                "state": "IN_PROGRESS",
                "risk": "medium",
                "quarter": "2026-Q3",
                "depends_on": ["FR-20260601-some-prereq"]
            },
            ...
        ],
        "quarters": {
            "2026-Q3": ["FR-20260630-cross-project-roadmap-generator", ...],
            "2026-Q4": [...]
        }
    }

If "quarters" is absent, buckets are derived by grouping nodes on their
own "quarter" field. If a node has no "quarter", it is bucketed under
"Unscheduled".
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_ROADMAP_PATH = Path(r"f:\⊕Workspace\src\data\roadmap.json")

# Canonical project order + color used for Gantt swimlanes. Kept in a fixed
# order so the swimlane list is stable regardless of data ordering.
CANONICAL_PROJECTS: list[str] = [
    "\u221eLife",
    "\u2764Music",
    "\u27e8\u03c8\u27e9Quantum",
    "\U0001f441AI-Manifest",
    "\u2295Workspace",
    "\u03a3Capital",
]

_PROJECT_COLORS: dict[str, str] = {
    "\u221eLife": "#6cc6ff",
    "\u2764Music": "#ff6f91",
    "\u27e8\u03c8\u27e9Quantum": "#a78bfa",
    "\U0001f441AI-Manifest": "#ffb86c",
    "\u2295Workspace": "#7ee787",
    "\u03a3Capital": "#f5c518",
    "Other": "#7a8aa3",
}

# ASCII/keyword fallbacks for matching project names that arrive with
# mojibake or plain-ASCII substitutions instead of the sigil prefix (the
# companion ⊕Workspace roadmap generator does not guarantee canonicalized
# project names as of this writing — see SCHEMA ASSUMPTION above).
_PROJECT_KEYWORDS: list[tuple[str, str]] = [
    ("life", "\u221eLife"),
    ("music", "\u2764Music"),
    ("quantum", "\u27e8\u03c8\u27e9Quantum"),
    ("manifest", "\U0001f441AI-Manifest"),
    ("workspace", "\u2295Workspace"),
    ("capital", "\u03a3Capital"),
]

_QUARTER_RE = re.compile(r"^\d{4}-Q[1-4]$")


def _canonical_project(name: str) -> str:
    """Normalize a raw project string to one of CANONICAL_PROJECTS, falling
    back to keyword matching for mojibake/ASCII variants, or "Other"."""
    if not name:
        return "Other"
    if name in CANONICAL_PROJECTS:
        return name
    lowered = name.lower()
    for keyword, canonical in _PROJECT_KEYWORDS:
        if keyword in lowered:
            return canonical
    return "Other"


def _quarter_sort_key(quarter: str) -> tuple[int, str]:
    """Sort valid YYYY-Qn quarters chronologically; push anything else last."""
    if _QUARTER_RE.match(quarter or ""):
        return (0, quarter)
    return (1, quarter or "")


def _format_quarter_label(quarter: str) -> str:
    if _QUARTER_RE.match(quarter or ""):
        year, q = quarter.split("-")
        return f"{q} {year}"
    return quarter or "Unscheduled"


def load_roadmap_data(path: Path | None = None) -> dict[str, Any]:
    """Load the roadmap JSON artifact. Returns an empty-but-valid structure
    if the file does not exist or cannot be parsed."""
    target = path or DEFAULT_ROADMAP_PATH
    empty: dict[str, Any] = {"generated_at": "", "nodes": [], "quarters": {}}
    if not target.exists():
        return empty
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty
    if not isinstance(data, dict):
        return empty
    data.setdefault("nodes", [])
    data.setdefault("quarters", {})
    data.setdefault("generated_at", "")
    return data


def _quarter_buckets(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group node dicts into quarter buckets, preferring an explicit
    'quarters' map (id lists) but falling back to each node's own 'quarter'."""
    nodes = data.get("nodes", [])
    by_id = {n.get("id"): n for n in nodes if n.get("id")}

    explicit = data.get("quarters") or {}
    if explicit:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for quarter, ids in explicit.items():
            buckets[quarter] = [by_id[i] for i in ids if i in by_id]
        return buckets

    buckets = {}
    for n in nodes:
        q = n.get("quarter") or "Unscheduled"
        buckets.setdefault(q, []).append(n)
    return buckets


def _risk_badge(risk: str) -> str:
    risk_l = (risk or "").lower()
    colors = {"low": "#3ddc84", "medium": "#f5c518", "high": "#ff5f5f"}
    color = colors.get(risk_l, "#7a8aa3")
    label = html.escape(risk or "unknown")
    return f'<span class="roadmap-risk" style="background:{color}22;color:{color};">{label}</span>'


def _dependency_graph_html(data: dict[str, Any]) -> str:
    """Render a simple readable dependency list, grouped by project, with
    arrows showing FR-to-FR dependency edges."""
    nodes = data.get("nodes", [])
    if not nodes:
        return '<p class="roadmap-empty">No roadmap data available yet.</p>'

    by_id = {n.get("id"): n for n in nodes if n.get("id")}
    by_project: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        proj = n.get("project") or "Unknown"
        by_project.setdefault(proj, []).append(n)

    sections = []
    for project in sorted(by_project.keys()):
        rows = []
        for n in by_project[project]:
            title = html.escape(n.get("title") or n.get("id", ""))
            state = html.escape(n.get("state") or "unknown")
            risk = _risk_badge(n.get("risk", ""))
            deps = n.get("depends_on") or []
            dep_labels = []
            for dep_id in deps:
                dep_node = by_id.get(dep_id)
                dep_title = html.escape(
                    (dep_node.get("title") if dep_node else None) or dep_id
                )
                dep_labels.append(dep_title)
            deps_html = (
                " &larr; " + ", ".join(dep_labels) if dep_labels else ""
            )
            rows.append(
                f'<li><strong>{title}</strong> '
                f'<span class="roadmap-state">[{state}]</span> '
                f'{risk}{deps_html}</li>'
            )
        sections.append(
            f'<div class="roadmap-project"><h4>{html.escape(project)}</h4>'
            f'<ul class="roadmap-deps">{"".join(rows)}</ul></div>'
        )
    return "\n".join(sections)


def _quarterly_plan_html(data: dict[str, Any]) -> str:
    """Render FRs grouped into quarter buckets."""
    buckets = _quarter_buckets(data)
    if not buckets:
        return '<p class="roadmap-empty">No quarterly milestones available yet.</p>'

    sections = []
    for quarter in sorted(buckets.keys()):
        items = buckets[quarter]
        rows = "".join(
            f"""<tr>
                <td>{html.escape(n.get('title') or n.get('id', ''))}</td>
                <td>{html.escape(n.get('project') or '')}</td>
                <td>{html.escape(n.get('state') or 'unknown')}</td>
                <td>{_risk_badge(n.get('risk', ''))}</td>
            </tr>"""
            for n in items
        )
        sections.append(
            f"""<div class="roadmap-quarter">
                <h4>{html.escape(quarter)}</h4>
                <table class="roadmap-quarter-table">
                    <thead><tr><th>FR</th><th>Project</th><th>State</th><th>Risk</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>"""
        )
    return "\n".join(sections)


def render_roadmap_tab_html(data: dict[str, Any] | None = None) -> str:
    """Render the full Roadmap tab panel HTML.

    v2 default view is a Gantt-style quarterly timeline (see _gantt_html).
    The legacy dependency-graph + quarterly-table rendering remains
    available via _dependency_graph_html / _quarterly_plan_html for callers
    that still want it, but is no longer used by default here per Tyler's
    request for a traditional Gantt view.
    """
    data = data if data is not None else load_roadmap_data()
    generated_at = html.escape(data.get("generated_at") or "unknown")

    return f"""
    <div class="roadmap-meta">Roadmap generated: {generated_at}</div>
    <h3>Quarterly Roadmap</h3>
    <div class="roadmap-gantt-wrap">
        {_gantt_html(data)}
    </div>
    """


def _milestone_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    """FR nodes only (ids starting with 'FR-'), in a near-final state, used
    as a lightweight proxy for release milestones. v1 simplification: no
    distinct "release" concept exists in the schema yet, so this is derived
    purely from state."""
    near_final_states = {
        "REVIEW_REQUESTED",
        "AUTO_REVIEWED",
        "TYLER_APPROVED",
        "SOAKING",
    }
    nodes = data.get("nodes", [])
    return [
        n
        for n in nodes
        if str(n.get("id", "")).startswith("FR-")
        and (n.get("state") or "").upper() in near_final_states
    ]


def _gantt_html(data: dict[str, Any]) -> str:
    """Render a CSS-grid Gantt-style quarterly timeline: quarter columns
    across the top, one swimlane row per canonical project, milestone
    markers row for near-final FRs. v1 simplification: each node's
    "quarter" field is treated as a single-quarter-width bar (start ==
    end) since the schema has no explicit end-quarter concept yet."""
    nodes = data.get("nodes", [])
    if not nodes:
        return '<p class="roadmap-empty">No roadmap data available yet.</p>'

    quarters = sorted(
        {n.get("quarter") for n in nodes if n.get("quarter")}, key=_quarter_sort_key
    )
    if not quarters:
        return '<p class="roadmap-empty">No roadmap data available yet.</p>'

    quarter_index = {q: i for i, q in enumerate(quarters)}
    n_cols = len(quarters)
    grid_template = f"200px repeat({n_cols}, 1fr)"

    def _col_style(q: str) -> str:
        i = quarter_index.get(q)
        if i is None:
            return ""
        return f"grid-column: {i + 2} / {i + 3};"

    header_cells = "".join(
        f'<div class="gantt-qhead">{html.escape(_format_quarter_label(q))}</div>'
        for q in quarters
    )

    milestones = _milestone_nodes(data)
    milestone_by_q: dict[str, list[str]] = {}
    for n in milestones:
        q = n.get("quarter")
        if q not in quarter_index:
            continue
        title = html.escape(n.get("title") or n.get("id", ""))
        milestone_by_q.setdefault(q, []).append(f"\U0001f680 {title}")
    milestone_cells = "".join(
        f'<div class="gantt-milestone-cell" style="{_col_style(q)}">'
        f'{"<br>".join(labels)}</div>'
        for q, labels in milestone_by_q.items()
    )

    by_project: dict[str, list[dict[str, Any]]] = {p: [] for p in CANONICAL_PROJECTS}
    for n in nodes:
        canonical = _canonical_project(n.get("project") or "")
        if canonical not in by_project:
            by_project[canonical] = []
        by_project[canonical].append(n)

    lane_rows = []
    for project in CANONICAL_PROJECTS:
        color = _PROJECT_COLORS.get(project, _PROJECT_COLORS["Other"])
        label = html.escape(project)
        bars = "".join(
            f'<div class="gantt-bar" style="{_col_style(n.get("quarter") or "")};'
            f'background:{color}33;border-left:3px solid {color};" '
            f'title="{html.escape(n.get("state") or "")}">'
            f'{html.escape(n.get("title") or n.get("id", ""))}</div>'
            for n in by_project.get(project, [])
            if n.get("quarter") in quarter_index
        )
        lane_rows.append(
            f"""<div class="gantt-row swimlane" style="grid-template-columns:{grid_template};">
                <div class="gantt-lane-label" style="border-left:4px solid {color};">{label}</div>
                <div class="gantt-lane-track" style="grid-column: 2 / -1; display:grid; grid-template-columns: repeat({n_cols}, 1fr);">
                    {bars}
                </div>
            </div>"""
        )

    return f"""
    <div class="gantt">
        <div class="gantt-row gantt-header" style="grid-template-columns:{grid_template};">
            <div class="gantt-corner"></div>
            {header_cells}
        </div>
        <div class="gantt-row gantt-milestones" style="grid-template-columns:{grid_template};">
            <div class="gantt-lane-label">Milestones</div>
            {milestone_cells}
        </div>
        {"".join(lane_rows)}
    </div>
    """


ROADMAP_STYLES = """
.tab-nav {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
}
.tab-pill {
    background: rgba(99, 130, 200, 0.12);
    border: 1px solid rgba(99, 130, 200, 0.25);
    color: #cfd8ea;
    border-radius: 999px;
    padding: 0.4rem 1.1rem;
    cursor: pointer;
    font-size: 0.9rem;
}
.tab-pill.active {
    background: rgba(99, 130, 200, 0.35);
    color: #fff;
}
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.roadmap-project { margin-bottom: 1rem; }
.roadmap-deps { list-style: none; padding-left: 0; }
.roadmap-deps li { padding: 0.25rem 0; }
.roadmap-risk {
    border-radius: 6px;
    padding: 0.05rem 0.5rem;
    font-size: 0.75rem;
    margin-left: 0.4rem;
}
.roadmap-quarter { margin-bottom: 1.25rem; }
.roadmap-quarter-table { width: 100%; border-collapse: collapse; }
.roadmap-quarter-table th, .roadmap-quarter-table td {
    padding: 0.35rem 0.6rem;
    border-bottom: 1px solid rgba(99, 130, 200, 0.15);
    text-align: left;
}
.roadmap-empty { color: #7a8aa3; font-style: italic; }

.gantt { display: flex; flex-direction: column; gap: 2px; overflow-x: auto; }
.gantt-row { display: grid; align-items: stretch; gap: 2px; }
.gantt-header .gantt-qhead {
    font-weight: 600;
    color: #cfd8ea;
    padding: 0.4rem 0.5rem;
    text-align: center;
    background: rgba(99, 130, 200, 0.10);
}
.gantt-corner { background: transparent; }
.gantt-milestones { min-height: 2.2rem; }
.gantt-milestones .gantt-lane-label {
    color: #cfd8ea;
    font-style: italic;
    padding: 0.35rem 0.5rem;
}
.gantt-milestone-cell {
    font-size: 0.8rem;
    color: #ffd479;
    padding: 0.25rem 0.4rem;
    text-align: center;
}
.gantt-lane-label {
    padding: 0.5rem 0.6rem;
    background: rgba(99, 130, 200, 0.08);
    border-radius: 4px;
    font-weight: 500;
    display: flex;
    align-items: center;
}
.gantt-lane-track { min-height: 2.4rem; align-items: center; }
.gantt-bar {
    border-radius: 4px;
    padding: 0.3rem 0.5rem;
    font-size: 0.82rem;
    color: #eef2fb;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    align-self: center;
}
"""

TAB_NAV_SCRIPT = """
function switchTab(name) {
    document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-pill').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.getElementById('pill-' + name).classList.add('active');
    localStorage.setItem('activeTab', name);
}

function restoreActiveTab() {
    var saved = localStorage.getItem('activeTab') || 'overview';
    if (document.getElementById('tab-' + saved) && document.getElementById('pill-' + saved)) {
        switchTab(saved);
    }
}
"""


def render_tab_nav_html() -> str:
    """Render the tab-nav pill bar (Overview / Roadmap)."""
    return """
    <div class="tab-nav">
        <button id="pill-overview" class="tab-pill active" onclick="switchTab('overview')">Overview</button>
        <button id="pill-roadmap" class="tab-pill" onclick="switchTab('roadmap')">Roadmap</button>
    </div>
    """
