"""Regression guards for retiring the AI-Manifest Ollama surfaces."""

from pathlib import Path


AI_MANIFEST_ROOT = Path(__file__).resolve().parents[1]


def test_ai_manifest_has_no_ollama_integration_package() -> None:
    integration_paths = tuple(
        AI_MANIFEST_ROOT.glob("src/**/ollama*")
    )

    assert not integration_paths


def test_ai_manifest_tests_have_no_ollama_client_path() -> None:
    test_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (AI_MANIFEST_ROOT / "tests").glob("test_*.py")
        if path.name != Path(__file__).name
    )

    assert "ollama" not in test_text