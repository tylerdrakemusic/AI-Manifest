"""AI-Manifest Ollama client wrapper.

This module delegates to the canonical Ollama client implementation from the
⊕Workspace project. It only adds a tiny import-time bootstrap so that the
shared Workspace package can be imported directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_WORKSPACE_ENV = "WORKSPACE_ROOT"


def _find_workspace_root() -> Path | None:
    env_path = os.environ.get(_WORKSPACE_ENV)
    if env_path:
        path = Path(env_path)
        if path.is_dir():
            return path

    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        workspace_dir = parent / "⊕Workspace"
        if workspace_dir.is_dir():
            return workspace_dir
        workspace_dir = parent / "workspace"
        if workspace_dir.is_dir():
            return workspace_dir

    drive_root = current.anchor
    for entry in Path(drive_root).iterdir():
        if not entry.is_dir():
            continue
        if entry.name == "⊕Workspace" or entry.name.endswith("Workspace") or entry.name.lower() == "workspace":
            return entry
    return None


_workspace_root = _find_workspace_root()
if _workspace_root is None:
    raise ImportError(
        "Workspace root not found; canonical Ollama client cannot be loaded. "
        "Set WORKSPACE_ROOT to the ⊕Workspace repo root or run inside the multi-root workspace."
    )

if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from src.integrations.ollama import OllamaClient, OllamaError, DEFAULT_BASE_URL, DEFAULT_MODEL, httpx

__all__ = [
    "OllamaClient",
    "OllamaError",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "httpx",
]
