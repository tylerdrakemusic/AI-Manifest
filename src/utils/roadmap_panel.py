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
from pathlib import Path
from typing import Any

DEFAULT_ROADMAP_PATH = Path(r"f:\⊕Workspace\src\data\roadmap.json")


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
    """Render the full Roadmap tab panel HTML (dependency graph + quarterly plan)."""
    data = data if data is not None else load_roadmap_data()
    generated_at = html.escape(data.get("generated_at") or "unknown")

    return f"""
    <div class="roadmap-meta">Roadmap generated: {generated_at}</div>
    <h3>Dependency Graph</h3>
    <div class="roadmap-graph">
        {_dependency_graph_html(data)}
    </div>
    <h3>Quarterly Milestone Plan</h3>
    <div class="roadmap-quarters">
        {_quarterly_plan_html(data)}
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
"""

TAB_NAV_SCRIPT = """
function switchTab(name) {
    document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-pill').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.getElementById('pill-' + name).classList.add('active');
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
