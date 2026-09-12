import json
from pathlib import Path

from tests.diagram_budget_helpers import (
    BUDGETS,
    DiagramCategory,
    DiagramSpec,
    Traceability,
    measure_source,
    validate_diagram,
)


DIAGRAM_DIR = Path(__file__).resolve().parents[1] / "diagrams"
EXPECTED_DIAGRAMS = {
    "manifest-architecture.mmd": ("graph ", None),
    "manifest-db-schema.mmd": ("erDiagram", None),
    "manifest-derived-media-pipeline.mmd": ("graph ", "diagrams/manifest-architecture.mmd"),
    "manifest-derived-portal-and-image.mmd": ("graph ", "diagrams/manifest-architecture.mmd"),
    "manifest-derived-todo-and-backup.mmd": ("graph ", "diagrams/manifest-architecture.mmd"),
    "manifest-tech-stack.mmd": ("graph ", None),
}
MAX_RENDERING_BYTES = 12_000
MANIFEST_PATH = DIAGRAM_DIR / "diagram-manifest.json"
KIND_TO_CATEGORY = {
    "architecture": DiagramCategory.OVERVIEW,
    "db-schema": DiagramCategory.DATABASE_SCHEMA,
    "derived-view": DiagramCategory.DETAIL,
    "tech-stack": DiagramCategory.TECHNOLOGY_STACK,
}


def test_manifest_mermaid_sources_are_local_utf8_within_budget_and_traceable() -> None:
    assert {path.name for path in DIAGRAM_DIR.glob("*.mmd")} == set(EXPECTED_DIAGRAMS)

    for filename, (entry_point, parent) in EXPECTED_DIAGRAMS.items():
        source_path = DIAGRAM_DIR / filename
        source_bytes = source_path.read_bytes()
        source = source_bytes.decode("utf-8")
        diagram_body = "\n".join(
            line for line in source.splitlines() if not line.startswith("%%")
        ).lstrip()

        assert len(source_bytes) <= MAX_RENDERING_BYTES
        assert diagram_body.startswith(entry_point)
        assert "-->" in source or "--" in source
        if parent is not None:
            assert "%% is_derived_view=true" in source
            assert f"%% Traceability.parent: {parent}" in source

    architecture = (DIAGRAM_DIR / "manifest-architecture.mmd").read_text(encoding="utf-8")
    assert "diagrams/manifest-derived-media-pipeline.mmd" in architecture
    assert "diagrams/manifest-derived-portal-and-image.mmd" in architecture
    assert "diagrams/manifest-derived-todo-and-backup.mmd" in architecture


def test_manifest_diagrams_satisfy_shared_budget_contract() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for record in payload["diagrams"]:
        source_path = Path(__file__).resolve().parents[1] / record["path"]
        metrics = measure_source(source_path)
        lineage = record["lineage"]
        result = validate_diagram(
            DiagramSpec(
                path=record["path"],
                category=KIND_TO_CATEGORY[record["kind"]],
                metrics=metrics,
                traceability=Traceability(
                    parent=lineage["parent"],
                    derived_views=tuple(lineage["derived_views"]),
                ),
                is_derived_view=record["kind"] == "derived-view",
            )
        )

        budget = BUDGETS[KIND_TO_CATEGORY[record["kind"]]]
        assert metrics.utf8_characters <= budget.max_utf8_characters
        assert metrics.utf8_bytes <= MAX_RENDERING_BYTES
        assert metrics.nodes > 0
        assert metrics.nodes <= budget.max_nodes
        assert metrics.edges <= budget.max_edges
        assert record["kind"] in {"architecture", "db-schema", "derived-view", "tech-stack"}
        assert record["split_required"] is result.split_required
        assert result.findings == (), f"{record['path']} findings={result.findings}"