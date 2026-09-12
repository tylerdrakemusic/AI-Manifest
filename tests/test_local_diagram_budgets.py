"""Test that AI-Manifest can import diagram utilities locally without Workspace."""

from __future__ import annotations

from src.utils.diagram_budgets import DiagramCategory


def test_diagram_category_enum_is_available_locally() -> None:
    """Validate DiagramCategory is available from local src.utils without cross-repo imports."""
    assert DiagramCategory.OVERVIEW == "overview"
    assert DiagramCategory.DETAIL == "detail"
    assert DiagramCategory.DATABASE_SCHEMA == "database-schema"
    assert DiagramCategory.TECHNOLOGY_STACK == "technology-stack"
