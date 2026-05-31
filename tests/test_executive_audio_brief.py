"""Unit tests for executive_audio_brief.py (non-Playwright).

BFX-20260530-remove-live-dash-chrome
BFX-20260530-lily-brief-priority-offload
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
_PORTAL_OUTPUT = Path(__file__).resolve().parent.parent / "output" / "executive_brief_portal.html"


def test_executive_audio_brief_source_has_no_static_banner() -> None:
    """BFX-20260530-remove-live-dash-chrome: source template must not contain static-banner."""
    src = (_TOOLS / "executive_audio_brief.py").read_text(encoding="utf-8")
    assert "static-banner" not in src, "executive_audio_brief.py still defines static-banner CSS/element"
    assert "Static snapshot" not in src, "executive_audio_brief.py still contains 'Static snapshot' text"


def test_executive_brief_portal_output_has_no_static_banner() -> None:
    """BFX-20260530-remove-live-dash-chrome: generated output HTML must not contain the toast."""
    if not _PORTAL_OUTPUT.exists():
        import pytest
        pytest.skip(f"Portal not generated — run executive_audio_brief.py first: {_PORTAL_OUTPUT}")
    html = _PORTAL_OUTPUT.read_text(encoding="utf-8")
    assert "static-banner" not in html, "executive_brief_portal.html still contains static-banner"
    assert "Static snapshot" not in html, "executive_brief_portal.html still contains 'Static snapshot' text"


# ---------------------------------------------------------------------------
# BFX-20260530-lily-brief-priority-offload tests
# ---------------------------------------------------------------------------

def _make_open_rows(items: list[dict]) -> list[dict]:
    """Helper: build minimal open-row dicts for mocking get_open_todos."""
    rows = []
    for i, item in enumerate(items):
        rows.append({
            "id": i + 1,
            "text": item["text"],
            "priority": item["priority"],
            "autonomy_level": item.get("autonomy_level", "human"),
            "source": item.get("source", "TEST"),
            "done": 0,
        })
    return rows


def test_gather_project_status_sorts_todos_by_priority() -> None:
    """Fix 1: full/supervised/human todos must be sorted by priority desc after filtering."""
    open_rows = _make_open_rows([
        {"text": "low full", "priority": 2, "autonomy_level": "full"},
        {"text": "high full", "priority": 9, "autonomy_level": "full"},
        {"text": "mid full", "priority": 5, "autonomy_level": "full"},
        {"text": "low sup", "priority": 1, "autonomy_level": "supervised"},
        {"text": "high sup", "priority": 8, "autonomy_level": "supervised"},
        {"text": "low human", "priority": 3, "autonomy_level": "human"},
        {"text": "high human", "priority": 7, "autonomy_level": "human"},
    ])

    project = {
        "sigil": "⊕",
        "name": "Workspace",
        "key": "workspace",
        "root": Path("f:/⊕Workspace"),
        "always_include": False,
        "priority_weight": 1,
    }

    with (
        patch("tools.executive_audio_brief.get_open_todos", return_value=open_rows),
        patch("tools.executive_audio_brief.get_done_todos", return_value=[]),
    ):
        from tools.executive_audio_brief import gather_project_status
        status = gather_project_status(project)

    full = status["full_todos"]
    assert [t["text"] for t in full] == ["high full", "mid full", "low full"], \
        f"full_todos not sorted desc by priority: {[t['priority'] for t in full]}"

    sup = status["supervised_todos"]
    assert [t["text"] for t in sup] == ["high sup", "low sup"], \
        f"supervised_todos not sorted desc by priority: {[t['priority'] for t in sup]}"

    human = status["human_todos"]
    assert [t["text"] for t in human] == ["high human", "low human"], \
        f"human_todos not sorted desc by priority: {[t['priority'] for t in human]}"


def test_generate_brief_script_covers_all_5_projects() -> None:
    """Fix 2: generate_brief_script must mention all 5 project names in the output."""
    from tools.executive_audio_brief import generate_brief_script

    statuses = [
        {"sigil": "❤", "name": "Music", "key": "music", "active_tasks": 5,
         "summary": "Music summary.", "full_todos": [], "score": 1050},
        {"sigil": "∞", "name": "Life", "key": "life", "active_tasks": 3,
         "summary": "Life summary.", "full_todos": [], "score": 15},
        {"sigil": "⟨ψ⟩", "name": "Quantum", "key": "quantum", "active_tasks": 2,
         "summary": "Quantum summary.", "full_todos": [], "score": 6},
        {"sigil": "👁", "name": "AI-Manifest", "key": "ai_manifest", "active_tasks": 1,
         "summary": "AI summary.", "full_todos": [], "score": 2},
        {"sigil": "⊕", "name": "Workspace", "key": "workspace", "active_tasks": 4,
         "summary": "Workspace summary.", "full_todos": [], "score": 4},
    ]

    script = generate_brief_script(statuses, "2026-05-30 12:00:00")

    for name in ["Music", "Life", "Quantum", "AI-Manifest", "Workspace"]:
        assert name in script, f"Project '{name}' missing from brief script"


def test_generate_brief_script_includes_offloadable_item() -> None:
    """Fix 3: if a project has full_todos, the top one must appear in the script."""
    from tools.executive_audio_brief import generate_brief_script

    statuses = [
        {"sigil": "❤", "name": "Music", "key": "music", "active_tasks": 2,
         "summary": "Music summary.", "score": 1050,
         "full_todos": [
             {"id": 1, "text": "Auto-generate release notes", "priority": 9},
             {"id": 2, "text": "Secondary offload task", "priority": 3},
         ]},
    ]

    script = generate_brief_script(statuses, "2026-05-30 12:00:00")
    assert "Fully offloadable: Auto-generate release notes" in script, \
        "Top full_todo text not found in script"


def test_generate_brief_script_skips_offload_when_none() -> None:
    """Fix 3: projects with no full_todos must not produce a 'Fully offloadable:' line."""
    from tools.executive_audio_brief import generate_brief_script

    statuses = [
        {"sigil": "⊕", "name": "Workspace", "key": "workspace", "active_tasks": 1,
         "summary": "Workspace summary.", "score": 4, "full_todos": []},
    ]

    script = generate_brief_script(statuses, "2026-05-30 12:00:00")
    assert "Fully offloadable:" not in script, \
        "Unexpected 'Fully offloadable:' line when full_todos is empty"
