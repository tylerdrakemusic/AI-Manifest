"""👁AI-Manifest Ollama integration.

This package delegates to the shared canonical Ollama client implementation
from the Workspace project when available, avoiding duplicate client code.

Callers can continue to import::

    from src.integrations.ollama import OllamaClient, OllamaError

    client = OllamaClient()
    reply = client.generate("Summarize the following: ...")
"""

from .client import OllamaClient, OllamaError

__all__ = ["OllamaClient", "OllamaError"]
