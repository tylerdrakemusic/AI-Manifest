"""Focused tests for normalized todo decision metadata."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from src.utils import todos_db

    db_file = tmp_path / "manifest_todos.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    todos_db.init_db()
    return db_file


def test_decision_metadata_round_trip_and_assessment_history(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Persist a decision", priority=4)
    metadata = {
        "expected_value": "Improves operational clarity.",
        "user_or_system_benefit": "Faster, more consistent triage.",
        "strategic_alignment": "Supports the shared todo contract.",
        "confidence": 8,
        "cost_of_delay": "Repeated manual rework.",
        "primary_benefit_category": "system",
        "secondary_benefit_category": "maintenance",
        "benefit_summary": "Standardized decisions reduce ambiguity.",
        "justification": "The same metadata contract is used across project slices.",
        "evidence": ["FR-20260827-workspace-todo-decision-metadata-standard"],
    }

    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")

    current = todos_db.get_decision_metadata(todo_id)
    history = todos_db.get_decision_assessments(todo_id)
    assert current == metadata
    assert len(history) == 1
    assert history[0]["metadata"] == metadata

    guidance = todos_db.get_priority_guidance(todo_id)
    assert guidance["recommended_priority"] == 8
    assert guidance["current_priority"] == 4
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 4


def test_invalid_scores_and_categories_are_rejected_without_writing(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Validate decisions")
    metadata = {
        "expected_value": "Useful.",
        "user_or_system_benefit": "Useful.",
        "strategic_alignment": "Useful.",
        "confidence": 11,
        "cost_of_delay": "Useful.",
        "primary_benefit_category": "invented",
        "benefit_summary": "Useful.",
        "justification": "Useful.",
        "evidence": ["observed"],
    }

    with pytest.raises(ValueError, match="primary_benefit_category"):
        todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")
    assert todos_db.get_decision_metadata(todo_id) is None


def test_high_impact_metadata_requires_evidence(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Require evidence", priority=9)
    metadata = {
        "expected_value": "High impact change.",
        "user_or_system_benefit": "Safer operation.",
        "strategic_alignment": "Reduces operational risk.",
        "confidence": 7,
        "cost_of_delay": "Continued risk.",
        "primary_benefit_category": "risk_reduction",
        "benefit_summary": "High impact change.",
        "justification": "High impact change.",
        "evidence": [],
    }

    with pytest.raises(ValueError, match="high-impact"):
        todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")


def test_canonical_metadata_rejects_legacy_field_names_and_unknown_categories(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Reject drift")
    metadata = {
        "expected_value": "Useful.",
        "user_or_system_benefit": "Useful.",
        "strategic_alignment": "Useful.",
        "confidence": 8,
        "cost_of_delay": "Useful.",
        "primary_benefit_category": "user",
        "benefit_summary": "Useful.",
        "justification": "Useful.",
        "evidence": ["observed"],
        "rationale": "legacy alias",
    }

    with pytest.raises(ValueError, match="unexpected"):
        todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")


def test_canonical_metadata_supports_optional_secondary_category(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Use canonical categories")
    metadata = {
        "expected_value": "Useful.",
        "user_or_system_benefit": "Useful.",
        "strategic_alignment": "Useful.",
        "confidence": 6,
        "cost_of_delay": "Useful.",
        "primary_benefit_category": "user",
        "benefit_summary": "Useful.",
        "justification": "Useful.",
        "evidence": ["observed"],
    }

    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")

    assert todos_db.get_decision_metadata(todo_id) == metadata


def test_legacy_todo_has_no_fabricated_decision_metadata(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Legacy row")

    assert todos_db.get_decision_metadata(todo_id) is None
    assert todos_db.get_decision_assessments(todo_id) == []


def test_reassessment_updates_current_but_preserves_history(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Retain assessments")
    first = {
        "expected_value": "Need more data.", "user_or_system_benefit": "Better evidence.",
        "strategic_alignment": "Improve decision quality.", "confidence": 4,
        "cost_of_delay": "Uncertainty persists.", "primary_benefit_category": "learning",
        "benefit_summary": "Need more data.", "justification": "Need more data.",
        "evidence": ["unknown"],
    }
    second = {**first, "confidence": 9, "justification": "Evidence arrived."}

    todos_db.set_decision_metadata(todo_id, first, assessed_by="agent-a")
    todos_db.set_decision_metadata(todo_id, second, assessed_by="agent-b")

    assert todos_db.get_decision_metadata(todo_id) == second
    history = todos_db.get_decision_assessments(todo_id)
    assert [item["metadata"] for item in history] == [first, second]


def test_init_db_adds_metadata_tables_without_fabricating_legacy_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.utils import todos_db

    db_file = tmp_path / "legacy.db"
    monkeypatch.setattr(todos_db, "DB_PATH", db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute("""
            CREATE TABLE todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO todos (id, project, source, text, created_at) VALUES (?,?,?,?,?)",
            (77, "ai_manifest", "TYLER", "Old todo", "2026-08-27T00:00:00+00:00"),
        )

    todos_db.init_db()

    with todos_db.get_connection() as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert {"todo_decision_metadata", "todo_decision_assessments"} <= tables
    assert todos_db.get_decision_metadata(77) is None
    assert todos_db.get_decision_assessments(77) == []


def test_explicit_priority_update_is_bounded_and_historized(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Keep priority explicit", priority=3)
    with pytest.raises(ValueError, match="1-10"):
        todos_db.update_priority(todo_id, 0)
    assert todos_db.update_priority(todo_id, 9) is True

    with todos_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT priority FROM priority_history WHERE todo_id=?", (todo_id,)
        ).fetchall()
    assert [row[0] for row in rows] == [9]
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 9