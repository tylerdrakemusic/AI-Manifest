# Capability Registry Contract

AI-Manifest exposes a versioned, provider-neutral catalog through
`src.capabilities.registry.CapabilityRegistry` and the read-only MCP server in
`src.integrations.capability_mcp_server`.

## Contract

Repository-owned `ProviderManifest` values contain a provider identifier,
manifest version, endpoint class, capabilities, known models, descriptive
constraints, and non-secret authentication requirements. Serialization returns
only those fields. It never reads credential values and never reports live
health, quota, freshness, routing, or generation results.

The first release registers `dall-e-3`, `elevenlabs`, `hugging-face`, and
`pollinations`. Results are sorted by provider identifier and can be filtered
by capability or modality. Missing providers raise a deterministic `KeyError`.

## MCP Surface

- `list_capability_providers`: list safe manifests, optionally by capability or modality
- `get_capability_provider`: retrieve one safe provider manifest
- `list_capability_models`: retrieve safe model metadata for one provider

These tools are read-only and delegate to the Python registry. They do not
perform HTTP calls, provider introspection, health checks, quota checks,
generation, or runtime routing.