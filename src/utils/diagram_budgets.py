"""Minimal local diagram budgets for AI-Manifest manifest validation.

This module provides the essential diagram category enum needed for local
manifest tests, eliminating the fragile cross-repo import dependency.
"""

from __future__ import annotations

from enum import Enum


class DiagramCategory(str, Enum):
    """Diagram classification for budget and rendering policy."""

    OVERVIEW = "overview"
    DETAIL = "detail"
    DATABASE_SCHEMA = "database-schema"
    TECHNOLOGY_STACK = "technology-stack"
    WORKFLOW = "workflow"
