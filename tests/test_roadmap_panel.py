"""Unit tests for src/utils/roadmap_panel.py — the Roadmap tab renderer used by
the executive brief portal.

FR-20260630-cross-project-roadmap-generator (👁AI-Manifest half).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.roadmap_panel import (
    load_roadmap_data,
    render_roadmap_tab_html,
    render_tab_nav_html,
    _quarter_buckets,
    _dependency_graph_html,
    _quarterly_plan_html,
    _canonical_project,
    _gantt_html,
    CANONICAL_PROJECTS,
)


SAMPLE_DATA = {
    "generated_at": "2026-06-30T00:00:00Z",
    "nodes": [
        {
            "id": "FR-A",
            "title": "Alpha Feature",
            "project": "❤Music",
            "state": "IN_PROGRESS",
            "risk": "medium",
            "quarter": "2026-Q3",
            "depends_on": [],
        },
        {
            "id": "FR-B",
            "title": "Beta Feature",
            "project": "∞Life",
            "state": "PLANNED",
            "risk": "high",
            "quarter": "2026-Q4",
            "depends_on": ["FR-A"],
        },
    ],
    "quarters": {
        "2026-Q3": ["FR-A"],
        "2026-Q4": ["FR-B"],
    },
}


def test_load_roadmap_data_missing_file_returns_empty_structure(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    data = load_roadmap_data(missing)
    assert data == {"generated_at": "", "nodes": [], "quarters": {}}


def test_load_roadmap_data_invalid_json_returns_empty_structure(tmp_path: Path) -> None:
    bad = tmp_path / "roadmap.json"
    bad.write_text("{not valid json", encoding="utf-8")
    data = load_roadmap_data(bad)
    assert data["nodes"] == []


def test_load_roadmap_data_reads_valid_file(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.json"
    path.write_text(json.dumps(SAMPLE_DATA), encoding="utf-8")
    data = load_roadmap_data(path)
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["id"] == "FR-A"


def test_quarter_buckets_uses_explicit_quarters_map() -> None:
    buckets = _quarter_buckets(SAMPLE_DATA)
    assert set(buckets.keys()) == {"2026-Q3", "2026-Q4"}
    assert buckets["2026-Q3"][0]["id"] == "FR-A"
    assert buckets["2026-Q4"][0]["id"] == "FR-B"


def test_quarter_buckets_falls_back_to_node_quarter_field() -> None:
    data = {
        "nodes": [
            {"id": "FR-X", "title": "X", "project": "⟨ψ⟩Quantum", "quarter": "2026-Q1"},
            {"id": "FR-Y", "title": "Y", "project": "⟨ψ⟩Quantum"},
        ],
        "quarters": {},
    }
    buckets = _quarter_buckets(data)
    assert buckets["2026-Q1"][0]["id"] == "FR-X"
    assert buckets["Unscheduled"][0]["id"] == "FR-Y"


def test_dependency_graph_html_groups_by_project_and_shows_edges() -> None:
    out = _dependency_graph_html(SAMPLE_DATA)
    assert "❤Music" in out
    assert "∞Life" in out
    assert "Alpha Feature" in out
    assert "Beta Feature" in out
    # Beta depends on Alpha — the dependency title should be shown as an edge label
    assert "Alpha Feature" in out.split("Beta Feature")[1]


def test_dependency_graph_html_empty_nodes_shows_placeholder() -> None:
    out = _dependency_graph_html({"nodes": [], "quarters": {}})
    assert "No roadmap data" in out


def test_quarterly_plan_html_renders_fr_title_project_state_risk() -> None:
    out = _quarterly_plan_html(SAMPLE_DATA)
    assert "2026-Q3" in out
    assert "2026-Q4" in out
    assert "Alpha Feature" in out
    assert "IN_PROGRESS" in out
    assert "medium" in out


def test_render_roadmap_tab_html_includes_generated_at_and_sections() -> None:
    out = render_roadmap_tab_html(SAMPLE_DATA)
    assert "2026-06-30T00:00:00Z" in out
    assert "Quarterly Roadmap" in out
    assert "Alpha Feature" in out


def test_render_tab_nav_html_includes_overview_and_roadmap_pills() -> None:
    out = render_tab_nav_html()
    assert "Overview" in out
    assert "Roadmap" in out
    assert "switchTab('roadmap')" in out


# ---------------------------------------------------------------------------
# Gantt-style quarterly timeline (FR-20260630 rework — v2)
# ---------------------------------------------------------------------------

GANTT_FIXTURE = {
    "generated_at": "2026-07-01T00:00:00Z",
    "nodes": [
        {
            "id": "FR-life-1",
            "title": "Longevity Dashboard Refresh",
            "project": "\u221eLife",
            "state": "DONE",
            "risk": "low",
            "quarter": "2026-Q1",
            "depends_on": [],
        },
        {
            "id": "FR-music-1",
            "title": "Catalog Ingest Pipeline",
            "project": "\u2764Music",
            "state": "IN_PROGRESS",
            "risk": "medium",
            "quarter": "2026-Q2",
            "depends_on": [],
        },
        {
            "id": "FR-quantum-1",
            "title": "VQE Benchmark Suite",
            "project": "\u27e8\u03c8\u27e9Quantum",
            "state": "REVIEW_REQUESTED",
            "risk": "medium",
            "quarter": "2026-Q3",
            "depends_on": [],
        },
        {
            "id": "FR-ai-1",
            "title": "Cross-Project Roadmap Generator",
            "project": "\U0001f441AI-Manifest",
            "state": "SOAKING",
            "risk": "medium",
            "quarter": "2026-Q3",
            "depends_on": [],
        },
        {
            "id": "FR-ws-1",
            "title": "Security Dashboard Hardening",
            "project": "\u2295Workspace",
            "state": "PLANNED",
            "risk": "high",
            "quarter": "2026-Q4",
            "depends_on": [],
        },
        {
            "id": "FR-cap-1",
            "title": "Schwab Order Guardrails",
            "project": "\u03a3Capital",
            "state": "TYLER_APPROVED",
            "risk": "high",
            "quarter": "2026-Q4",
            "depends_on": [],
        },
    ],
    "quarters": {},
}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("\u221eLife", "\u221eLife"),
        ("infinitelife", "\u221eLife"),
        ("\u2764Music", "\u2764Music"),
        ("?Music", "\u2764Music"),
        ("\u27e8\u03c8\u27e9Quantum", "\u27e8\u03c8\u27e9Quantum"),
        ("Quantum", "\u27e8\u03c8\u27e9Quantum"),
        ("\U0001f441AI-Manifest", "\U0001f441AI-Manifest"),
        ("AI-Manifest", "\U0001f441AI-Manifest"),
        ("\u2295Workspace", "\u2295Workspace"),
        ("?Workspace", "\u2295Workspace"),
        ("\u03a3Capital", "\u03a3Capital"),
        ("Capital", "\u03a3Capital"),
        ("Something Else", "Other"),
    ],
)
def test_canonical_project_normalizes_variants(raw: str, expected: str) -> None:
    assert _canonical_project(raw) == expected


def test_gantt_html_renders_all_canonical_swimlanes() -> None:
    out = _gantt_html(GANTT_FIXTURE)
    for project in CANONICAL_PROJECTS:
        assert html_escape_safe(project) in out


def html_escape_safe(s: str) -> str:
    import html as _html

    return _html.escape(s)


def test_gantt_html_renders_bars_in_correct_quarter_columns() -> None:
    out = _gantt_html(GANTT_FIXTURE)
    assert "Longevity Dashboard Refresh" in out
    assert "Catalog Ingest Pipeline" in out
    assert "Q1 2026" in out
    assert "Q4 2026" in out


def test_gantt_html_includes_milestones_row_for_near_final_frs() -> None:
    out = _gantt_html(GANTT_FIXTURE)
    assert "Milestones" in out
    # SOAKING and REVIEW_REQUESTED are near-final states — should surface
    assert "Cross-Project Roadmap Generator" in out.split("Milestones")[1].split(
        "swimlane"
    )[0] or "Cross-Project Roadmap Generator" in out


def test_gantt_html_empty_nodes_shows_placeholder() -> None:
    out = _gantt_html({"nodes": [], "quarters": {}})
    assert "No roadmap data" in out


def test_render_roadmap_tab_html_defaults_to_gantt_view() -> None:
    out = render_roadmap_tab_html(GANTT_FIXTURE)
    assert "gantt" in out.lower()
    assert "Q1 2026" in out
