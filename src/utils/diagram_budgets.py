r"""Minimal local diagram budgets for AI-Manifest manifest validation.

This module provides diagram validation essentials needed for local manifest tests,
eliminating the fragile cross-repo import dependency on Workspace.
Extracted minimal subset from F:\⊕Workspace\src\utils\diagram_budgets.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DiagramCategory(str, Enum):
    """Diagram classification for budget and rendering policy."""

    OVERVIEW = "overview"
    DETAIL = "detail"
    DATABASE_SCHEMA = "database-schema"
    TECHNOLOGY_STACK = "technology-stack"
    WORKFLOW = "workflow"


@dataclass(frozen=True)
class DiagramMetrics:
    """Measured properties of a Mermaid diagram source."""
    utf8_characters: int
    utf8_bytes: int
    nodes: int
    edges: int
    renderer_url_risk: str
    fallback_risk: str


@dataclass(frozen=True)
class Traceability:
    """Lineage metadata for diagram dependencies."""
    parent: str | None
    derived_views: tuple[str, ...]


@dataclass(frozen=True)
class DiagramSpec:
    """Complete specification of a diagram for validation."""
    path: str
    category: DiagramCategory
    metrics: DiagramMetrics
    traceability: Traceability
    is_derived_view: bool = False


@dataclass(frozen=True)
class Finding:
    """Validation issue found during budget check."""
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Result of diagram validation including findings and split status."""
    findings: tuple[Finding, ...]
    split_required: bool


def measure_source(path: Path) -> DiagramMetrics:
    """Measure a Mermaid source file for budget compliance."""
    with path.open("r", encoding="utf-8", newline="") as source_file:
        source = source_file.read()
    source = source.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    lines = source.splitlines()
    
    # Count nodes and edges using heuristic parsing
    node_count = sum(1 for line in lines if _looks_like_node(line))
    edge_count = sum(1 for line in lines if any(
        operator in line for operator in ("-->", "==>", "-.->", "---", "===", "}|")
    ))
    
    return DiagramMetrics(
        utf8_characters=len(source),
        utf8_bytes=len(source.encode("utf-8")),
        nodes=node_count,
        edges=edge_count,
        renderer_url_risk="low",
        fallback_risk="medium" if ("%%{init:" in source or not source.isascii()) else "low",
    )


def _looks_like_node(line: str) -> bool:
    """Heuristic check if a line declares a graph node."""
    # Simple check for common Mermaid node patterns
    stripped = line.strip()
    if not stripped or stripped.startswith("graph"):
        return False
    if any(stripped.startswith(marker) for marker in ("-->", "==>", "-.->", "---", "===", "}|")):
        return False
    if "[" in stripped or "(" in stripped or "{" in stripped:
        return True
    return False


def validate_diagram(spec: DiagramSpec) -> ValidationResult:
    """Validate a diagram against basic budget rules."""
    findings: list[Finding] = []
    split_required = False
    
    # Derived views must have parent
    if spec.is_derived_view and not spec.traceability.parent:
        findings.append(Finding("traceability", "derived views must name their parent diagram"))
    
    # Parent diagrams must declare derived views or empty list
    if not spec.is_derived_view and any(not view for view in spec.traceability.derived_views):
        findings.append(Finding("traceability", "parent diagrams must declare non-empty derived view paths"))
    
    return ValidationResult(findings=tuple(findings), split_required=split_required)
