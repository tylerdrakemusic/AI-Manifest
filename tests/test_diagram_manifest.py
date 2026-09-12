from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, r"F:\⊕Workspace")

from src.utils.diagram_budgets import DiagramCategory, DiagramSpec, Traceability, measure_source, validate_diagram


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "diagrams" / "diagram-manifest.json"
EXPECTED_SOURCES = {
    "diagrams/manifest-architecture.mmd",
    "diagrams/manifest-db-schema.mmd",
    "diagrams/manifest-derived-media-pipeline.mmd",
    "diagrams/manifest-derived-portal-and-image.mmd",
    "diagrams/manifest-derived-todo-and-backup.mmd",
    "diagrams/manifest-tech-stack.mmd",
}
KIND_TO_CATEGORY = {
    "architecture": DiagramCategory.OVERVIEW,
    "db-schema": DiagramCategory.DATABASE_SCHEMA,
    "derived-view": DiagramCategory.DETAIL,
    "tech-stack": DiagramCategory.TECHNOLOGY_STACK,
}


def test_manifest_declares_all_local_sources_and_derived_lineage() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["repository"] == "manifest"
    records = {record["path"]: record for record in payload["diagrams"]}
    assert set(records) == EXPECTED_SOURCES
    assert records["diagrams/manifest-architecture.mmd"]["lineage"] == {
        "parent": None,
        "derived_views": [
            "diagrams/manifest-derived-media-pipeline.mmd",
            "diagrams/manifest-derived-portal-and-image.mmd",
            "diagrams/manifest-derived-todo-and-backup.mmd",
        ],
    }
    assert records["diagrams/manifest-derived-media-pipeline.mmd"]["lineage"] == {
        "parent": "diagrams/manifest-architecture.mmd",
        "derived_views": [],
    }
    assert records["diagrams/manifest-derived-portal-and-image.mmd"]["lineage"] == {
        "parent": "diagrams/manifest-architecture.mmd",
        "derived_views": [],
    }
    assert records["diagrams/manifest-derived-todo-and-backup.mmd"]["lineage"] == {
        "parent": "diagrams/manifest-architecture.mmd",
        "derived_views": [],
    }


def test_manifest_paths_resolve_to_local_mermaid_sources() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for record in payload["diagrams"]:
        source_path = MANIFEST_PATH.parents[1] / record["path"]
        assert source_path.is_file()
        assert source_path.suffix == ".mmd"
        assert record["renderer_risk"] == "low"
        assert record["fallback_risk"] == "medium"
        metrics = measure_source(source_path)
        result = validate_diagram(
            DiagramSpec(
                path=record["path"],
                category=KIND_TO_CATEGORY[record["kind"]],
                metrics=metrics,
                traceability=Traceability(
                    parent=record["lineage"]["parent"],
                    derived_views=tuple(record["lineage"]["derived_views"]),
                ),
                is_derived_view=record["kind"] == "derived-view",
            )
        )
        assert record["split_required"] is result.split_required