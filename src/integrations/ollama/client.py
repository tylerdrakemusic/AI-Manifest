"""AI-Manifest Ollama client wrapper.

This module delegates to the canonical Ollama client implementation from the
⊕Workspace project. It loads the shared Workspace client by path and
re-exports the shared client symbols so AI-Manifest does not duplicate
Ollama API logic.

In CI and local multi-root development, set the WORKSPACE_ROOT environment
variable to the root path of the ⊕Workspace checkout.

Import from any project via::

    import os
    import sys
    from pathlib import Path

    workspace_root = Path(os.environ.get('WORKSPACE_ROOT', r'f:\⊕Workspace'))
    sys.path.insert(0, str(workspace_root))
    from src.integrations.ollama import OllamaClient

Environment variables
---------------------
OLLAMA_BASE_URL : base URL of the running Ollama server
    Default: http://localhost:11434
OLLAMA_MODEL : model tag to use for generation
    Default: llama3.1:8b
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_WORKSPACE_ENV = 'WORKSPACE_ROOT'


def _find_workspace_root() -> Path | None:
    env_path = os.environ.get(_WORKSPACE_ENV)
    if env_path:
        path = Path(env_path)
        if path.is_dir():
            return path

    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / '⊕Workspace'
        if candidate.is_dir():
            return candidate
        candidate = parent / 'workspace'
        if candidate.is_dir():
            return candidate

    drive_root = current.anchor
    for entry in Path(drive_root).iterdir():
        if not entry.is_dir():
            continue
        if (
            entry.name == '⊕Workspace'
            or entry.name.endswith('Workspace')
            or entry.name.lower() == 'workspace'
        ):
            return entry
    return None


_workspace_root = _find_workspace_root()
if _workspace_root is None:
    raise ImportError(
        'Workspace root not found; canonical Ollama client cannot be loaded. '
        'Set WORKSPACE_ROOT to the ⊕Workspace repo root or run inside the multi-root workspace.'
    )

_workspace_client_path = (
    _workspace_root / 'src' / 'integrations' / 'ollama' / 'client.py'
)
if not _workspace_client_path.is_file():
    raise ImportError(
        f'Workspace Ollama client not found at {_workspace_client_path!s}. '
        'Check that the shared ⊕Workspace repository is checked out correctly.'
    )

_spec = importlib.util.spec_from_file_location(
    'workspace_ollama_client',
    str(_workspace_client_path),
)
if _spec is None or _spec.loader is None:
    raise ImportError(
        f'Failed to load workspace Ollama client spec from {_workspace_client_path!s}'
    )

_workspace_module = importlib.util.module_from_spec(_spec)
sys.modules['workspace_ollama_client'] = _workspace_module
_spec.loader.exec_module(_workspace_module)

OllamaClient = _workspace_module.OllamaClient
OllamaError = _workspace_module.OllamaError
DEFAULT_BASE_URL = _workspace_module.DEFAULT_BASE_URL
DEFAULT_MODEL = _workspace_module.DEFAULT_MODEL
httpx = _workspace_module.httpx

__all__ = [
    'OllamaClient',
    'OllamaError',
    'DEFAULT_BASE_URL',
    'DEFAULT_MODEL',
    'httpx',
]
