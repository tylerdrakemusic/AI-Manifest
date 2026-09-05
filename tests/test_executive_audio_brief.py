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


def test_orbit_desk_template_removes_deprioritized_scanning_content() -> None:
    """Orbit Desk keeps the scan surface focused on status, actions, and roadmap."""
    src = (_TOOLS / "executive_audio_brief.py").read_text(encoding="utf-8")

    for removed in (".subtitle", "#controls", ".controls {{", ".orbit-desk-actions {{",
                    "#serveHint", ".audio-meta", ".summary", ".offload-subtitle",
                    "#scriptSection"):
        assert removed not in src

    assert "max_width=180" in src


def test_orbit_desk_status_accents_are_muted_against_dark_surfaces() -> None:
    """Status badges and progress fills should support scanning without glowing."""
    src = (_TOOLS / "executive_audio_brief.py").read_text(encoding="utf-8")

    assert "background: rgba(213, 243, 107, 0.14);" in src
    assert "color: var(--accent-green);" in src
    assert "background: linear-gradient(90deg, #879d5c, #5797ad);" in src
    assert "color: #c58e4a;" in src


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


def test_gather_project_status_summary_does_not_duplicate_visible_todos() -> None:
    """Project summaries retain completion metrics without repeating TODO text."""
    open_rows = _make_open_rows([
        {"text": "Visible TODO text", "priority": 9, "autonomy_level": "supervised"},
    ])
    project = {
        "sigil": "⊕", "name": "Workspace", "key": "workspace",
        "root": Path(__file__).resolve().parent.parent,
        "always_include": False, "priority_weight": 1,
    }

    with (
        patch("tools.executive_audio_brief.get_open_todos", return_value=open_rows),
        patch("tools.executive_audio_brief.get_done_todos", return_value=[{"id": 99}]),
    ):
        from tools.executive_audio_brief import gather_project_status
        status = gather_project_status(project)

    assert status["summary"] == "⊕Workspace: 1 open tasks, 1 completed (50% done)."
    assert "Top priorities:" not in status["summary"]
    assert "Visible TODO text" not in status["summary"]


def test_gather_project_status_preserves_provenance_fields_for_each_view_model() -> None:
    """Every autonomy view model must retain identity and independent provenance fields."""
    open_rows = [
        {"id": 227, "text": "Perfected only", "priority": 9, "autonomy_level": "full", "source": "TYLER",
         "fr_id": None, "perfected_at": "2026-08-09T00:00:00+00:00"},
        {"id": 228, "text": "Linked only", "priority": 8, "autonomy_level": "supervised", "source": "AI",
         "fr_id": "FR-20260809-example", "perfected_at": None},
        {"id": 229, "text": "Both signals", "priority": 7, "autonomy_level": "human", "source": "SCAN",
         "fr_id": "FR-20260809-example", "perfected_at": "2026-08-10T00:00:00+00:00"},
    ]
    project = {
        "sigil": "⊕", "name": "Workspace", "key": "workspace", "root": Path("f:/⊕Workspace"),
        "always_include": False, "priority_weight": 1,
    }

    with (
        patch("tools.executive_audio_brief.get_open_todos", return_value=open_rows),
        patch("tools.executive_audio_brief.get_done_todos", return_value=[]),
    ):
        from tools.executive_audio_brief import gather_project_status
        status = gather_project_status(project)

    for view_name, todo_id in (("full_todos", 227), ("supervised_todos", 228), ("human_todos", 229)):
        todo = status[view_name][0]
        assert todo["id"] == todo_id
        assert "fr_id" in todo
        assert "perfected_at" in todo


def test_todo_classification_uses_execution_state_before_readiness() -> None:
    from tools.executive_audio_brief import classify_todo

    assert classify_todo({"id": 1, "done": 0, "execution_state": "claimed"}, {}) == "claimed"
    assert classify_todo({"id": 2, "done": 0, "execution_state": "running"}, {}) == "running"
    assert classify_todo({"id": 3, "done": 1, "closure_reason": "stale"}, {}) == "stale"
    assert classify_todo({"id": 4, "done": 0, "execution_state": "failed", "retry_eligible": True}, {}) == "retry-eligible"
    assert classify_todo({"id": 5, "done": 0}, {5: False}) == "blocked"
    assert classify_todo({"id": 6, "done": 0}, {6: True}) == "runnable"


def test_build_todo_hierarchy_keeps_runnable_children_inline_and_collapses_other_children() -> None:
    from tools.executive_audio_brief import build_todo_hierarchy

    rows = [
        {"id": 10, "text": "Parent", "done": 0, "parent_id": None, "priority": 8},
        {"id": 11, "text": "Runnable child", "done": 0, "parent_id": 10, "priority": 9},
        {"id": 12, "text": "Blocked child", "done": 0, "parent_id": 10, "priority": 7},
    ]

    hierarchy = build_todo_hierarchy(rows, {11: True, 12: False})

    assert len(hierarchy) == 1
    assert hierarchy[0]["parent"]["id"] == 10
    assert [child["id"] for child in hierarchy[0]["inline_children"]] == [11]
    assert [child["id"] for child in hierarchy[0]["collapsed_children"]] == [12]
    assert hierarchy[0]["expanded_by_default"] is False


def test_build_todo_hierarchy_supports_cross_domain_parents_and_nested_children() -> None:
    from tools.executive_audio_brief import build_todo_hierarchy

    rows = [
        {"id": 300, "text": "Root", "done": 0, "parent_id": None, "priority": 9, "project": "workspace"},
        {"id": 304, "text": "Nested parent", "done": 0, "parent_id": 300, "priority": 8, "project": "workspace"},
        {"id": 324, "text": "Nested child", "done": 0, "parent_id": 304, "priority": 7, "project": "workspace"},
        {"id": 349, "text": "Cross-domain child", "done": 0, "parent_id": 307, "priority": 6, "project": "quantum"},
        {"id": 307, "text": "Cross-domain parent", "done": 0, "parent_id": None, "priority": 9, "project": "workspace"},
        {"id": 350, "text": "Completed child", "done": 1, "parent_id": 307, "priority": 5, "project": "ai_manifest"},
    ]

    hierarchy = build_todo_hierarchy(rows, {324: True, 349: False, 350: True})

    assert [group["parent"]["id"] for group in hierarchy] == [300, 307]
    root = hierarchy[0]
    nested_parent = root["inline_children"][0]
    assert nested_parent["id"] == 304
    assert [child["id"] for child in nested_parent["children"]] == [324]
    cross_domain = hierarchy[1]
    assert [child["id"] for child in cross_domain["inline_children"]] == []
    assert [child["id"] for child in cross_domain["collapsed_children"]] == [349]
    assert "Completed child" not in str(hierarchy)


def test_gather_project_status_keeps_cross_domain_ancestor_context() -> None:
    from tools.executive_audio_brief import gather_project_status

    parent = {"id": 307, "text": "Cross-domain parent", "done": 0, "parent_id": None,
              "priority": 9, "project": "workspace", "autonomy_level": "full", "source": "TYLER"}
    child = {"id": 349, "text": "Cross-domain child", "done": 0, "parent_id": 307,
             "priority": 6, "project": "quantum", "autonomy_level": "human", "source": "TYLER"}
    project = {
        "sigil": "⟨ψ⟩", "name": "Quantum", "key": "quantum", "root": Path("f:/⟨ψ⟩Quantum"),
        "always_include": False, "priority_weight": 1,
    }

    def open_todos(project_key=None):
        return [child] if project_key == "quantum" else [parent, child]

    with (
        patch("tools.executive_audio_brief.get_open_todos", side_effect=open_todos),
        patch("tools.executive_audio_brief.get_done_todos", return_value=[]),
        patch("tools.executive_audio_brief.get_readiness", return_value={"ready": True}),
    ):
        status = gather_project_status(project)

    rendered = str(status["todo_hierarchy"])
    assert "Cross-domain parent" in rendered
    assert "Cross-domain child" in rendered


def test_parent_rows_collapse_the_full_child_queue_and_copy_full_text() -> None:
    from tools.executive_audio_brief import _todo_hierarchy_html

    hierarchy = [{
        "parent": {"id": 10, "text": "A very long parent title", "priority": 8, "source": "AI"},
        "inline_children": [{"id": 11, "text": "Runnable child", "priority": 9, "source": "AI", "state": "runnable"}],
        "collapsed_children": [{"id": 12, "text": "Blocked child", "priority": 7, "source": "AI", "state": "blocked"}],
        "aggregate_state": "runnable",
        "join_status": "2 children · 1 runnable",
    }]

    output = _todo_hierarchy_html(hierarchy, "⊕", "Workspace")

    assert 'aria-expanded="false"' in output
    assert "A very long parent title" in output
    assert "2 children · 1 runnable" in output
    assert 'title="A very long parent title"' in output
    assert 'class="todo-collapsed-children" hidden' in output
    assert output.index("Runnable child") < output.index("Blocked child")
    assert 'onclick="copyTodoText(this)"' in output
    assert 'data-copy-text="A very long parent title"' in output
    assert 'data-copy-text="Runnable child"' in output
    assert 'data-copy-text="Blocked child"' in output
    assert 'onclick="markDone(10, this)"' in output
    assert 'onclick="cancelTodo(10, this)"' in output
    parent_primary = output.split('<div class="todo-meta">', 1)[0]
    assert '<span class="todo-state">' not in parent_primary
    assert "runNext" not in output
    assert "Execution queue" not in output


def test_status_card_renders_ids_and_independent_provenance_signals_without_changing_done_target() -> None:
    from tools.executive_audio_brief import _status_card_html

    status = {
        "sigil": "⊕", "name": "Workspace", "key": "workspace", "summary": "Workspace summary.",
        "active_tasks": 3, "completed_tasks": 0, "full_todos": [],
        "supervised_todos": [
            {"id": 227, "text": "Perfected only", "priority": 9, "source": "TYLER",
             "fr_id": None, "perfected_at": "2026-08-09T00:00:00+00:00"},
            {"id": 228, "text": "Linked only", "priority": 8, "source": "AI",
             "fr_id": "FR-20260809-example", "perfected_at": None},
        ],
        "human_todos": [],
    }

    out = _status_card_html(status, 1)

    assert "TODO #227" in out
    assert "TODO #228" in out
    assert out.count('class="todo-signal perfected-badge"') == 0
    assert out.count('class="todo-signal signal-refined"') == 0
    assert out.count('class="todo-signal"') == 1
    assert out.count('<span class="todo-signal') == 3
    assert "PERFECTED" in out
    assert "Not perfected" not in out
    assert "FR linked" in out
    assert "No FR link" in out
    assert "priority-hint" not in out
    assert "leave blank" not in out
    assert 'onclick="markDone(227, this)"' in out
    assert 'onclick="markDone(228, this)"' in out


def test_status_card_layout_keeps_todo_text_readable_alongside_signal_rail() -> None:
    from tools.executive_audio_brief import generate_portal_html

    status = {
        "sigil": "⊕", "name": "Workspace", "key": "workspace", "summary": "Workspace summary.",
        "active_tasks": 1, "completed_tasks": 0, "full_todos": [],
        "supervised_todos": [
            {"id": 229, "text": "A deliberately long TODO title that must remain readable", "priority": 9,
             "source": "AI", "fr_id": "FR-20260809-example", "perfected_at": None},
        ],
        "human_todos": [],
    }

    out = generate_portal_html([status], "Brief script", None, [], "2026-08-10T00:00:00+00:00")

    assert ".todo-list li {" in out
    assert "grid-template-columns:" in out
    assert ".todo-text {" in out
    assert "display: block;" in out
    assert "max-width: 100%;" in out
    assert '"text text"' in out
    assert '"state actions"' in out
    assert "min-width: 0;" in out
    assert "overflow-wrap: anywhere;" in out
    assert "line-height: 1.45;" in out
    assert ".todo-signal {" in out
    assert "min-width: 7.5rem;" in out
    assert 'content: "☐ ";' not in out


def test_portal_styles_distinguish_execution_states() -> None:
    """Execution states have dedicated visual treatments in the generated CSS."""
    from tools.executive_audio_brief import generate_portal_html

    out = generate_portal_html([], "Brief script", None, [], "2026-08-10T00:00:00+00:00")

    for state in ("runnable", "blocked", "claimed", "running", "retry-eligible"):
        assert f'[data-state="{state}"]' in out
    assert '.todo-state::before' not in out


def test_status_card_todo_rows_render_primary_text_before_metadata() -> None:
    from tools.executive_audio_brief import generate_portal_html

    status = {
        "sigil": "⊕", "name": "Workspace", "key": "workspace", "summary": "Workspace summary.",
        "active_tasks": 1, "completed_tasks": 0, "full_todos": [],
        "supervised_todos": [
            {"id": 230, "text": "A readable primary TODO block", "priority": 9,
             "source": "AI", "fr_id": "FR-20260809-example", "perfected_at": None},
        ],
        "human_todos": [],
    }

    out = generate_portal_html([status], "Brief script", None, [], "2026-08-10T00:00:00+00:00")

    primary_start = out.index('<div class="todo-primary">')
    meta_start = out.index('<div class="todo-meta">')
    assert primary_start < meta_start
    assert '<div class="todo-meta">' in out and '<span class="todo-id">TODO #230</span>' in out
    assert '<div class="todo-primary"><span class="todo-text">' in out
    assert 'onclick="markDone(230, this)"' in out
    assert ".todo-meta {" in out
    assert ".todo-primary {" in out


def test_status_card_todo_rows_have_stable_non_overlapping_spacing() -> None:
    """The open-row marker must be anchored in a dedicated text gutter."""
    from tools.executive_audio_brief import generate_portal_html

    status = {
            "sigil": "⊕",
            "name": "Workspace",
            "key": "workspace",
            "summary": "Workspace summary.",
            "active_tasks": 1,
            "completed_tasks": 0,
            "full_todos": [],
            "supervised_todos": [{
                "id": 231,
                "text": "A readable task without a checkbox gutter",
                "priority": 8,
                "source": "TYLER",
                "perfected_at": None,
                "fr_id": None,
            }],
            "human_todos": [],
    }

    out = generate_portal_html(
        [status],
        "Brief script",
        None,
        [],
        "2026-08-10T00:00:00+00:00",
    )

    assert "position: relative;" in out
    assert "padding: 0.25rem 0;" in out
    assert 'content: "☐ ";' not in out
    assert "padding-left: 0;" in out
    assert 'grid-template-areas:\n        "primary"\n        "meta";' in out
    assert "min-width: 0;" in out
    assert "overflow-wrap: anywhere;" in out


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


# ---------------------------------------------------------------------------
# FR-20260630-cross-project-roadmap-generator — Roadmap tab wiring tests
# ---------------------------------------------------------------------------

def _minimal_status(sigil: str, name: str, key: str) -> dict:
    return {
        "sigil": sigil, "name": name, "key": key,
        "summary": f"{name} summary.", "active_tasks": 1, "completed_tasks": 1,
        "full_todos": [], "supervised_todos": [], "human_todos": [], "score": 10,
    }


def test_generate_portal_html_includes_roadmap_tab_and_pill() -> None:
    """The generated portal must include the Roadmap tab-pill and tab-panel,
    wired automatically into the existing generation pipeline."""
    from tools.executive_audio_brief import generate_portal_html

    statuses = [_minimal_status("⊕", "Workspace", "workspace")]

    with patch(
        "tools.executive_audio_brief.load_roadmap_data",
        return_value={
            "generated_at": "2026-06-30T00:00:00Z",
            "nodes": [
                {"id": "FR-A", "title": "Alpha", "project": "⊕Workspace",
                 "state": "IN_PROGRESS", "risk": "medium", "quarter": "2026-Q3",
                 "depends_on": []},
            ],
            "quarters": {"2026-Q3": ["FR-A"]},
        },
    ):
        out = generate_portal_html(statuses, "script", None, [], "2026-06-30 00:00:00")

    assert 'id="pill-roadmap"' in out, "Roadmap tab pill missing from generated portal HTML"
    assert 'id="tab-roadmap"' in out, "Roadmap tab panel missing from generated portal HTML"
    assert 'id="tab-overview"' in out, "Overview tab panel missing from generated portal HTML"
    assert "Alpha" in out, "Roadmap FR title not rendered in generated portal HTML"
    assert "Q3 2026" in out, "Roadmap quarter column not rendered in generated portal HTML"


def test_generate_portal_html_roadmap_tab_handles_missing_roadmap_data() -> None:
    """When no roadmap.json exists yet, the Roadmap tab must still render
    (with a placeholder) rather than raising or breaking the pipeline."""
    from tools.executive_audio_brief import generate_portal_html

    statuses = [_minimal_status("⊕", "Workspace", "workspace")]

    with patch(
        "tools.executive_audio_brief.load_roadmap_data",
        return_value={"generated_at": "", "nodes": [], "quarters": {}},
    ):
        out = generate_portal_html(statuses, "script", None, [], "2026-06-30 00:00:00")

    assert 'id="tab-roadmap"' in out
    assert "No roadmap data" in out


# ---------------------------------------------------------------------------
# BFX-20260701-roadmap-tab-follow-up — tab persistence + roadmap regen tests
# ---------------------------------------------------------------------------

def test_tab_nav_script_persists_and_restores_active_tab() -> None:
    """AC2: switchTab must save to localStorage and a restoreActiveTab
    function must read it back (defaulting to 'overview')."""
    from src.utils.roadmap_panel import TAB_NAV_SCRIPT

    assert "localStorage.setItem('activeTab', name)" in TAB_NAV_SCRIPT, \
        "switchTab does not persist the active tab to localStorage"
    assert "function restoreActiveTab" in TAB_NAV_SCRIPT, \
        "restoreActiveTab function missing from TAB_NAV_SCRIPT"
    assert "localStorage.getItem('activeTab')" in TAB_NAV_SCRIPT, \
        "restoreActiveTab does not read the saved tab back from localStorage"
    assert "'overview'" in TAB_NAV_SCRIPT, \
        "restoreActiveTab does not default to 'overview'"


def test_generate_portal_html_wires_restore_active_tab_on_load() -> None:
    """AC2: the generated portal must call restoreActiveTab() on page load
    so the 60s auto-refresh reload doesn't reset to Overview."""
    from tools.executive_audio_brief import generate_portal_html

    statuses = [_minimal_status("⊕", "Workspace", "workspace")]

    with patch(
        "tools.executive_audio_brief.load_roadmap_data",
        return_value={"generated_at": "", "nodes": [], "quarters": {}},
    ), patch("tools.executive_audio_brief._regenerate_roadmap_data"):
        out = generate_portal_html(statuses, "script", None, [], "2026-06-30 00:00:00")

    assert "restoreActiveTab" in out, \
        "generated portal HTML does not wire up restoreActiveTab() on load"


def test_regenerate_roadmap_data_invokes_expected_command() -> None:
    """AC1: portal build must attempt to regenerate roadmap.json via the
    ⊕Workspace roadmap_generator.py before reading it."""
    from tools.executive_audio_brief import (
        _regenerate_roadmap_data,
        ROADMAP_GENERATOR_SCRIPT,
        ROADMAP_JSON_OUTPUT_PATH,
    )

    with patch("tools.executive_audio_brief.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        _regenerate_roadmap_data()

    assert mock_run.called, "_regenerate_roadmap_data did not invoke subprocess.run"
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert str(ROADMAP_GENERATOR_SCRIPT) in cmd, "roadmap_generator.py script path not in invoked command"
    assert "--out" in cmd, "--out flag not in invoked command"
    assert str(ROADMAP_JSON_OUTPUT_PATH) in cmd, "roadmap.json output path not in invoked command"
    assert kwargs.get("check") is False


def test_regenerate_roadmap_data_swallows_failures() -> None:
    """AC1: a failed regeneration (exception) must not propagate/crash the portal build."""
    from tools.executive_audio_brief import _regenerate_roadmap_data

    with patch("tools.executive_audio_brief.subprocess.run", side_effect=OSError("boom")):
        _regenerate_roadmap_data()  # must not raise


def test_generate_portal_html_still_renders_when_regen_fails() -> None:
    """AC1: even if regeneration fails, the Roadmap tab must still render
    using whatever roadmap.json state exists on disk."""
    from tools.executive_audio_brief import generate_portal_html

    statuses = [_minimal_status("⊕", "Workspace", "workspace")]

    with patch(
        "tools.executive_audio_brief.load_roadmap_data",
        return_value={"generated_at": "", "nodes": [], "quarters": {}},
    ), patch("tools.executive_audio_brief.subprocess.run", side_effect=OSError("boom")):
        out = generate_portal_html(statuses, "script", None, [], "2026-06-30 00:00:00")

    assert 'id="tab-roadmap"' in out
    assert "No roadmap data" in out


def test_open_todo_surfaces_render_accessible_done_and_cancel_controls() -> None:
    """Card and fully-offloadable rows expose both terminal actions."""
    from tools.executive_audio_brief import _offload_panel_html, _status_card_html

    card = _status_card_html({
        "sigil": "⊕", "name": "Workspace", "key": "workspace", "summary": "Summary",
        "active_tasks": 1, "completed_tasks": 0,
        "supervised_todos": [{"id": 301, "text": "Card task", "priority": 7}],
        "human_todos": [], "full_todos": [],
    }, 1)
    offload = _offload_panel_html([{
        "sigil": "⊕", "name": "Workspace",
        "full_todos": [{"id": 302, "text": "Offload task", "priority": 8}],
    }])

    for output, todo_id in ((card, 301), (offload, 302)):
        assert f' onclick="markDone({todo_id}, this)"' in output or f" onclick=\"markDone({todo_id}, this)\"" in output
        assert f'cancelTodo({todo_id}, this)' in output
        assert f'aria-label="Mark TODO #{todo_id} done"' in output or f"aria-label='Mark TODO #{todo_id} done'" in output
        assert f'aria-label="Cancel TODO #{todo_id}"' in output or f"aria-label='Cancel TODO #{todo_id}'" in output


def test_portal_script_confirms_cancellation_and_posts_to_dedicated_api() -> None:
    from tools.executive_audio_brief import generate_portal_html

    status = _minimal_status("⊕", "Workspace", "workspace")
    status["supervised_todos"] = [{"id": 303, "text": "Confirm me", "priority": 5}]
    with patch("tools.executive_audio_brief._regenerate_roadmap_data"):
        out = generate_portal_html([status], "script", None, [], "2026-06-30 00:00:00")

    assert "window.confirm('Cancel this todo?')" in out
    assert "fetch('/api/todo/cancel'" in out
