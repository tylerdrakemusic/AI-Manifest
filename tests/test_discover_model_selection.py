"""RED phase: model auto-selection logic in discover_todos.py.

AC-1: Model auto-detection with fallback preference order.
AC-4: --model CLI override skips auto-detection entirely.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS = str(_REPO_ROOT / "tools")

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)


def _load_dt():
    """Fresh import of discover_todos to avoid stale module state."""
    if "discover_todos" in sys.modules:
        del sys.modules["discover_todos"]
    import discover_todos
    return discover_todos


def _make_list_result(names: list[str]) -> MagicMock:
    """Build a mock subprocess.run result for `ollama list` with the given model names."""
    header = "NAME                    ID              SIZE   MODIFIED\n"
    body = "".join(f"{name:<40} abc123  4 GB   2 days ago\n" for name in names)
    m = MagicMock()
    m.stdout = header + body
    m.returncode = 0
    return m


# ---------------------------------------------------------------------------
# AC-4: --model override
# ---------------------------------------------------------------------------

def test_model_arg_skips_subprocess() -> None:
    """When override is given, subprocess is never called."""
    dt = _load_dt()
    with patch("subprocess.run") as mock_sub:
        model = dt._select_model(override="mistral:7b")
    assert model == "mistral:7b"
    mock_sub.assert_not_called()


# ---------------------------------------------------------------------------
# AC-1: preferred model (llama3.3:70b found directly)
# ---------------------------------------------------------------------------

def test_prefers_llama33_70b_when_available() -> None:
    """If llama3.3:70b is in `ollama list`, use it with a single subprocess call."""
    dt = _load_dt()
    list_result = _make_list_result(["llama3.3:70b", "llama3.1:8b"])
    with patch("subprocess.run", return_value=list_result):
        model = dt._select_model()
    assert model == "llama3.3:70b"


# ---------------------------------------------------------------------------
# AC-1: fallback to any 70b when llama3.3:70b absent
# ---------------------------------------------------------------------------

def test_falls_back_to_any_70b_when_preferred_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to the first available 70b model when llama3.3:70b not found."""
    dt = _load_dt()
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    list_result = _make_list_result(["llama3:70b", "llama3.1:8b"])
    pull_result = MagicMock(returncode=1)
    with patch("subprocess.run", side_effect=[list_result, pull_result]):
        model = dt._select_model()
    assert "70b" in model


# ---------------------------------------------------------------------------
# AC-1: fallback to llama3.1:8b when no 70b or 13b present
# ---------------------------------------------------------------------------

def test_falls_back_to_8b_when_no_70b_or_13b(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to llama3.1:8b when only 8b models are available."""
    dt = _load_dt()
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    list_result = _make_list_result(["llama3.1:8b"])
    pull_result = MagicMock(returncode=1)
    with patch("subprocess.run", side_effect=[list_result, pull_result]):
        model = dt._select_model()
    assert model == "llama3.1:8b"


# ---------------------------------------------------------------------------
# AC-1: OLLAMA_MODELS env var set when preferred absent
# ---------------------------------------------------------------------------

def test_ollama_models_env_set_when_preferred_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OLLAMA_MODELS is set to F:\\.ollama\\models when llama3.3:70b not found."""
    dt = _load_dt()
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    list_result = _make_list_result(["llama3.1:8b"])
    pull_result = MagicMock(returncode=1)
    with patch("subprocess.run", side_effect=[list_result, pull_result]):
        dt._select_model()
    assert os.environ.get("OLLAMA_MODELS") == r"F:\.ollama\models"
