"""AI-Manifest Ollama client shim.

This module delegates to the shared canonical Ollama client implementation
in the Workspace project (``⊕Workspace/src/integrations/ollama/client.py``)
when available in the multi-root workspace.

If the workspace root cannot be discovered, the import fails with a clear
message explaining the missing shared implementation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _find_workspace_root() -> Path | None:
    drive_root = Path(__file__).resolve().anchor
    for entry in Path(drive_root).iterdir():
        if not entry.is_dir():
            continue
        if entry.name == "⊕Workspace" or entry.name.endswith("Workspace") or "Workspace" in entry.name:
            return entry
    return None


def _load_workspace_client() -> ModuleType:
    workspace_root = _find_workspace_root()
    if workspace_root is None:
        raise ImportError(
            "Workspace root not found on the drive; shared Ollama client cannot be loaded. "
            "Ensure the ⊕Workspace project is present in the same multi-root workspace."
        )

    client_path = (
        workspace_root
        / "src"
        / "integrations"
        / "ollama"
        / "client.py"
    )
    if not client_path.exists():
        raise ImportError(
            f"Shared Ollama client not found at {client_path}."
        )

    spec = importlib.util.spec_from_file_location(
        "workspace_ollama_client",
        str(client_path),
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load shared Ollama client from {client_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_workspace_client = _load_workspace_client()
OllamaClient = _workspace_client.OllamaClient
OllamaError = _workspace_client.OllamaError
DEFAULT_BASE_URL = _workspace_client.DEFAULT_BASE_URL
DEFAULT_MODEL = _workspace_client.DEFAULT_MODEL
httpx = _workspace_client.httpx

__all__ = [
    "OllamaClient",
    "OllamaError",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "httpx",
]
