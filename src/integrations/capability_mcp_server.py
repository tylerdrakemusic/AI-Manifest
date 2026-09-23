"""Read-only MCP discovery tools for the capability registry."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.capabilities.registry import CapabilityRegistry

mcp = FastMCP("AI-Manifest Capability Registry")
_registry = CapabilityRegistry()


@mcp.tool()
def list_capability_providers(
    capability: str | None = None,
    modality: str | None = None,
) -> list[dict[str, Any]]:
    """List safe provider manifests, optionally filtered by capability or modality."""
    return [item.to_dict() for item in _registry.list_providers(capability=capability, modality=modality)]


@mcp.tool()
def get_capability_provider(provider_id: str) -> dict[str, Any]:
    """Return safe metadata for one provider."""
    return _registry.get_provider(provider_id).to_dict()


@mcp.tool()
def list_capability_models(provider_id: str) -> list[dict[str, object]]:
    """Return safe model metadata for one provider."""
    return list(_registry.list_models(provider_id))


if __name__ == "__main__":
    mcp.run(transport="stdio")