"""Validation and persistence contract for TODO decision metadata."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


BENEFIT_CATEGORIES = frozenset({
    "user", "system", "strategic", "revenue", "risk_reduction",
    "learning", "maintenance", "compliance",
})
SCORE_FIELDS = (
    "expected_value", "user_or_system_benefit", "strategic_alignment",
    "confidence", "cost_of_delay",
)
REQUIRED_FIELDS = frozenset({
    *SCORE_FIELDS, "primary_benefit_category", "benefit_summary",
    "justification", "evidence",
})
OPTIONAL_FIELDS = frozenset({"secondary_benefit_category"})
SCALE_ANCHORS = {
    "min": 1,
    "max": 10,
    "anchors": {
        1: "minimal",
        3: "low",
        5: "moderate",
        7: "strong",
        8: "high",
        9: "very high",
        10: "exceptional",
    },
}


class DecisionMetadataError(ValueError):
    """Raised when TODO decision metadata violates the shared contract."""


def _score(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise DecisionMetadataError(f"{field} must be an integer from 1 to 10")
    return value


def validate_decision_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a decision metadata mapping."""
    if not isinstance(metadata, dict):
        raise DecisionMetadataError("metadata must be an object")

    missing = REQUIRED_FIELDS.difference(metadata)
    if missing:
        raise DecisionMetadataError(f"missing required fields: {sorted(missing)!r}")
    supported_fields = REQUIRED_FIELDS | OPTIONAL_FIELDS | {"scale"}
    unsupported = set(metadata).difference(supported_fields)
    if unsupported:
        raise DecisionMetadataError(f"unsupported fields: {sorted(unsupported)!r}")
    if "scale" in metadata and metadata["scale"] != SCALE_ANCHORS:
        raise DecisionMetadataError("scale must use the canonical 1-10 anchors")

    category = metadata["primary_benefit_category"]
    if category not in BENEFIT_CATEGORIES:
        raise DecisionMetadataError("primary_benefit_category is not supported")
    secondary = metadata.get("secondary_benefit_category")
    if secondary is not None and secondary not in BENEFIT_CATEGORIES:
        raise DecisionMetadataError("secondary_benefit_category is not supported")
    normalized = dict(metadata)
    scores = {field: _score(metadata[field], field) for field in SCORE_FIELDS}
    normalized.update(scores)

    for field in ("benefit_summary", "justification"):
        if not isinstance(metadata[field], str) or not metadata[field].strip():
            raise DecisionMetadataError(f"{field} must be a non-empty string")

    evidence = metadata.get("evidence")
    if not isinstance(evidence, list):
        raise DecisionMetadataError("evidence must be a list")
    if not all(isinstance(item, str) and item.strip() for item in evidence):
        raise DecisionMetadataError("evidence items must be non-empty strings")
    impact = max(scores.values())
    if impact >= 8 and not evidence:
        raise DecisionMetadataError("high-impact metadata requires evidence")
    if impact >= 9 and len(evidence) < 2:
        raise DecisionMetadataError("very high-impact metadata requires two evidence items")

    normalized["scale"] = {
        "min": SCALE_ANCHORS["min"],
        "max": SCALE_ANCHORS["max"],
        "anchors": dict(SCALE_ANCHORS["anchors"]),
    }
    return normalized


def priority_guidance(metadata: dict[str, Any], current_priority: int) -> dict[str, Any]:
    """Return advisory priority guidance without changing the supplied metadata."""
    if isinstance(current_priority, bool) or not isinstance(current_priority, int) or not 1 <= current_priority <= 10:
        raise DecisionMetadataError("current_priority must be an integer from 1 to 10")
    validated = validate_decision_metadata(metadata)
    signal = sum(validated[field] for field in SCORE_FIELDS) / len(SCORE_FIELDS)
    recommended = min(10, max(1, round(signal)))
    return {
        "current_priority": current_priority,
        "recommended_priority": recommended,
        "advisory": True,
    }


class DecisionMetadataStore:
    """Persist current metadata and immutable assessment history for TODOs."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def migrate(self) -> None:
        """Apply the additive metadata migration safely more than once."""
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(todos)")
        }
        if "decision_metadata" not in columns:
            self.connection.execute("ALTER TABLE todos ADD COLUMN decision_metadata TEXT")
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS todo_decision_metadata_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                todo_id INTEGER NOT NULL,
                metadata TEXT NOT NULL,
                assessed_at TEXT NOT NULL
            )"""
        )
        self.connection.commit()

    def save(self, todo_id: int, metadata: dict[str, Any]) -> None:
        """Validate and atomically replace current metadata while appending history."""
        normalized = validate_decision_metadata(metadata)
        serialized = json.dumps(normalized, sort_keys=True)
        assessed_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "UPDATE todos SET decision_metadata=? WHERE id=?",
                (serialized, todo_id),
            )
            self.connection.execute(
                "INSERT INTO todo_decision_metadata_history (todo_id, metadata, assessed_at) VALUES (?, ?, ?)",
                (todo_id, serialized, assessed_at),
            )

    def read_current(self, todo_id: int) -> dict[str, Any] | None:
        """Read current metadata, returning None for an unassessed legacy TODO."""
        row = self.connection.execute(
            "SELECT decision_metadata FROM todos WHERE id=?", (todo_id,)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return json.loads(row[0])

    def read_history(self, todo_id: int) -> list[dict[str, Any]]:
        """Read append-only assessments in insertion order."""
        rows = self.connection.execute(
            "SELECT metadata FROM todo_decision_metadata_history WHERE todo_id=? ORDER BY id",
            (todo_id,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]