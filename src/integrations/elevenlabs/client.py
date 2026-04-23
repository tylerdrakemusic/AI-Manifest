"""ElevenLabs API client — re-export shim.

The canonical implementation lives in the shared workspace integration library:
    f:\\⊕Workspace\\src\\integrations\\elevenlabs\\client.py

This module re-exports ElevenLabsClient for backwards compatibility with
existing 👁AI-Manifest imports.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the workspace client via absolute path to avoid module-name collision
# (both repos share the `src.integrations.elevenlabs` namespace).
_WORKSPACE_CLIENT = Path(r"f:\⊕Workspace\src\integrations\elevenlabs\client.py")
_WORKSPACE_SETTINGS = Path(r"f:\⊕Workspace\src\integrations\elevenlabs\settings.py")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_settings = _load_module("_workspace_elevenlabs_settings", _WORKSPACE_SETTINGS)
# The workspace client inlines its own constants, so just load it directly.
_client_mod = _load_module("_workspace_elevenlabs_client", _WORKSPACE_CLIENT)

ElevenLabsClient = _client_mod.ElevenLabsClient
DEFAULT_MODEL_ID = _settings.DEFAULT_MODEL_ID
DEFAULT_OUTPUT_FORMAT = _settings.DEFAULT_OUTPUT_FORMAT
DEFAULT_VOICE_SETTINGS = _settings.DEFAULT_VOICE_SETTINGS
STREAM_CHUNK_SIZE = _settings.STREAM_CHUNK_SIZE

__all__ = [
    "ElevenLabsClient",
    "DEFAULT_MODEL_ID",
    "DEFAULT_OUTPUT_FORMAT",
    "DEFAULT_VOICE_SETTINGS",
    "STREAM_CHUNK_SIZE",
]
