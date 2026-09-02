from pathlib import Path


DIAGRAM_DIR = Path(__file__).resolve().parents[1] / "diagrams"
EXPECTED_DIAGRAMS = {
    "manifest-architecture.mmd": ("graph ", None),
    "manifest-db-schema.mmd": ("erDiagram", None),
    "manifest-derived-media-pipeline.mmd": ("graph ", "diagrams/manifest-architecture.mmd"),
    "manifest-derived-todo-and-backup.mmd": ("graph ", "diagrams/manifest-architecture.mmd"),
    "manifest-tech-stack.mmd": ("graph ", None),
}
MAX_RENDERING_BYTES = 12_000


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
    assert "diagrams/manifest-derived-todo-and-backup.mmd" in architecture