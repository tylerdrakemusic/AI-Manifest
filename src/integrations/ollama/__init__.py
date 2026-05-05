"""👁AI-Manifest local Ollama integration.

Self-contained mirror of the workspace canonical Ollama client so that
AI-Manifest can run in CI without a cross-project sys.path hack.

Re-exports the primary client so callers can write::

    from src.integrations.ollama import OllamaClient, OllamaError

    client = OllamaClient()
    reply = client.generate("Summarize the following: ...")
"""

from .client import OllamaClient, OllamaError

__all__ = ["OllamaClient", "OllamaError"]
