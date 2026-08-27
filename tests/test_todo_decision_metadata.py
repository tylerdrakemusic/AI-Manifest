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
    from src.utils import todo_decision_metadata, todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Persist a decision", priority=4)
    metadata = {
        "expected_value": 8,
        "user_or_system_benefit": 7,
        "strategic_alignment": 8,
        "confidence": 8,
        "cost_of_delay": 7,
        "primary_benefit_category": "system",
        "secondary_benefit_category": "maintenance",
        "benefit_summary": "Standardized decisions reduce ambiguity.",
        "justification": "The same metadata contract is used across project slices.",
        "evidence": ["FR-20260827-workspace-todo-decision-metadata-standard"],
    }

    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")
    metadata = todo_decision_metadata.validate_decision_metadata(metadata)

    current = todos_db.get_decision_metadata(todo_id)
    history = todos_db.get_decision_assessments(todo_id)
    assert current == metadata
    assert len(history) == 1
    assert history[0]["metadata"] == metadata

    guidance = todos_db.get_priority_guidance(todo_id)
    assert guidance["recommended_priority"] == 8
    assert guidance["current_priority"] == 4
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 4


def test_public_setter_persists_canonical_integer_metadata_and_normalized_history(tmp_db: Path) -> None:
    from src.utils import todo_decision_metadata, todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Persist canonical metadata", priority=4)
    metadata = {
        "expected_value": 8,
        "user_or_system_benefit": 7,
        "strategic_alignment": 6,
        "confidence": 7,
        "cost_of_delay": 8,
        "primary_benefit_category": "risk_reduction",
        "benefit_summary": "Reduces repeated operational failures.",
        "justification": "The canonical contract is shared across project boundaries.",
        "evidence": ["test: public persistence path"],
        "scale": todo_decision_metadata.SCALE_ANCHORS,
    }

    expected = todo_decision_metadata.validate_decision_metadata(metadata)
    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")

    assert todos_db.get_decision_metadata(todo_id) == expected
    assert todos_db.get_decision_assessments(todo_id)[0]["metadata"] == expected


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
        "expected_value": 8,
        "user_or_system_benefit": 8,
        "strategic_alignment": 8,
        "confidence": 7,
        "cost_of_delay": 8,
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
        "expected_value": 5,
        "user_or_system_benefit": 5,
        "strategic_alignment": 5,
        "confidence": 8,
        "cost_of_delay": 5,
        "primary_benefit_category": "user",
        "benefit_summary": "Useful.",
        "justification": "Useful.",
        "evidence": ["observed"],
        "rationale": "legacy alias",
    }

    with pytest.raises(ValueError, match="unsupported"):
        todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")


def test_canonical_metadata_supports_optional_secondary_category(tmp_db: Path) -> None:
    from src.utils import todo_decision_metadata, todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Use canonical categories")
    metadata = {
        "expected_value": 5,
        "user_or_system_benefit": 5,
        "strategic_alignment": 5,
        "confidence": 6,
        "cost_of_delay": 5,
        "primary_benefit_category": "user",
        "benefit_summary": "Useful.",
        "justification": "Useful.",
        "evidence": ["observed"],
    }

    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="agent")

    assert todos_db.get_decision_metadata(todo_id) == todo_decision_metadata.validate_decision_metadata(metadata)


def test_legacy_todo_has_no_fabricated_decision_metadata(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Legacy row")

    assert todos_db.get_decision_metadata(todo_id) is None
    assert todos_db.get_decision_assessments(todo_id) == []


def test_reassessment_updates_current_but_preserves_history(tmp_db: Path) -> None:
    from src.utils import todo_decision_metadata, todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Retain assessments")
    first = {
        "expected_value": 4, "user_or_system_benefit": 4,
        "strategic_alignment": 4, "confidence": 4,
        "cost_of_delay": 4, "primary_benefit_category": "learning",
        "benefit_summary": "Need more data.", "justification": "Need more data.",
        "evidence": ["unknown"],
    }
    second = {
        **first,
        "confidence": 9,
        "justification": "Evidence arrived.",
        "evidence": ["unknown", "test: evidence arrived"],
    }

    first = todo_decision_metadata.validate_decision_metadata(first)
    second = todo_decision_metadata.validate_decision_metadata(second)

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


def test_canonical_score_fields_are_integer_1_to_10_and_expose_scale_anchors() -> None:
    from src.utils.todo_decision_metadata import SCORE_FIELDS, SCALE_ANCHORS, validate_decision_metadata

    metadata = {
        "expected_value": 8,
        "user_or_system_benefit": 7,
        "strategic_alignment": 6,
        "confidence": 7,
        "cost_of_delay": 8,
        "primary_benefit_category": "risk_reduction",
        "benefit_summary": "Reduces repeated operational failures.",
        "justification": "The change addresses a measured failure mode.",
        "evidence": ["test: measured failure mode"],
    }

    normalized = validate_decision_metadata(metadata)

    assert all(isinstance(normalized[field], int) for field in SCORE_FIELDS)
    assert all(1 <= normalized[field] <= 10 for field in SCORE_FIELDS)
    assert normalized["scale"] == SCALE_ANCHORS


def test_public_persistence_path_uses_versioned_canonical_contract(tmp_db: Path) -> None:
    from src.utils import todo_decision_contract, todo_decision_metadata, todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Use the governed contract")
    metadata = {
        "expected_value": 8,
        "user_or_system_benefit": 7,
        "strategic_alignment": 6,
        "confidence": 7,
        "cost_of_delay": 8,
        "primary_benefit_category": "system",
        "benefit_summary": "A shared contract prevents drift.",
        "justification": "The public setter must enforce the governed boundary.",
        "evidence": ["test: contract boundary"],
    }

    assert todo_decision_metadata.CONTRACT_VERSION == todo_decision_contract.VERSION
    assert todo_decision_metadata.SCORE_FIELDS == todo_decision_contract.SCORE_FIELDS
    assert todo_decision_metadata.BENEFIT_CATEGORIES == todo_decision_contract.BENEFIT_CATEGORIES
    assert todo_decision_metadata.SCALE_ANCHORS == todo_decision_contract.SCALE_ANCHORS
    assert todos_db.ALLOWED_BENEFIT_CATEGORIES == tuple(todo_decision_contract.BENEFIT_CATEGORIES)
    assert not hasattr(todos_db, "_validate_decision_metadata")

    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="contract-test")
    expected = todo_decision_metadata.validate_decision_metadata(metadata)
    assert todos_db.get_decision_metadata(todo_id) == expected
    assert todos_db.get_decision_assessments(todo_id)[0]["metadata"] == expected


def test_priority_guidance_uses_all_scores_and_remains_advisory(tmp_db: Path) -> None:
    from src.utils import todos_db

    todo_id = todos_db.add_todo("ai_manifest", "Calculate advisory guidance", priority=3)
    metadata = {
        "expected_value": 1,
        "user_or_system_benefit": 10,
        "strategic_alignment": 1,
        "confidence": 10,
        "cost_of_delay": 1,
        "primary_benefit_category": "learning",
        "benefit_summary": "Mixed signals need an aggregate recommendation.",
        "justification": "Advisory guidance must use the full score set.",
        "evidence": ["test: aggregate guidance", "test: second evidence"],
    }

    todos_db.set_decision_metadata(todo_id, metadata, assessed_by="contract-test")

    guidance = todos_db.get_priority_guidance(todo_id)
    assert guidance == {
        "todo_id": todo_id,
        "current_priority": 3,
        "recommended_priority": 5,
        "advisory": True,
    }
    assert todos_db.get_todo_by_id(todo_id)["priority"] == 3