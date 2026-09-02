from __future__ import annotations

import json
from pathlib import Path


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "diagrams" / "diagram-manifest.json"
EXPECTED_SOURCES = {
    "diagrams/manifest-architecture.mmd",
    "diagrams/manifest-db-schema.mmd",
    "diagrams/manifest-derived-media-pipeline.mmd",
    "diagrams/manifest-derived-todo-and-backup.mmd",
    "diagrams/manifest-tech-stack.mmd",
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
            "diagrams/manifest-derived-todo-and-backup.mmd",
        ],
    }
    assert records["diagrams/manifest-derived-media-pipeline.mmd"]["lineage"] == {
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