from __future__ import annotations

import pytest

from src.capabilities.models import AuthRequirement, Capability, ProviderManifest
from src.capabilities.registry import CapabilityRegistry
from src.integrations import capability_mcp_server
from src.integrations.capability_mcp_server import (
    get_capability_provider,
    list_capability_models,
    list_capability_providers,
)


def test_registry_discovers_four_providers_with_secret_safe_metadata() -> None:
    registry = CapabilityRegistry()

    providers = registry.list_providers()

    assert [provider.provider_id for provider in providers] == [
        "dall-e-3",
        "elevenlabs",
        "hugging-face",
        "pollinations",
    ]
    serialized = [provider.to_dict() for provider in providers]
    assert all("secret" not in str(item).lower() for item in serialized)
    assert all("health" not in item for item in serialized)
    assert all("quota" not in item for item in serialized)


def test_registry_filters_by_capability_and_modality() -> None:
    registry = CapabilityRegistry()

    assert [item.provider_id for item in registry.list_providers(capability="voice_synthesis")] == [
        "elevenlabs"
    ]
    assert [item.provider_id for item in registry.list_providers(modality="image")] == [
        "dall-e-3",
        "hugging-face",
        "pollinations",
    ]


def test_registry_not_found_is_deterministic() -> None:
    with pytest.raises(KeyError, match="provider not found: missing"):
        CapabilityRegistry().get_provider("missing")


def test_manifest_schema_rejects_empty_capability_sets() -> None:
    with pytest.raises(ValueError, match="at least one capability"):
        ProviderManifest(
            provider_id="invalid",
            display_name="Invalid",
            manifest_version="1.0",
            endpoint_class="test",
            capabilities=(),
            models=(),
            constraints=(),
            authentication=(),
        )


def test_auth_configuration_rejects_credential_shaped_values() -> None:
    manifest = ProviderManifest(
        provider_id="custom-provider",
        display_name="Custom Provider",
        manifest_version="1.0",
        endpoint_class="test",
        capabilities=(Capability("test", "text", "Test capability."),),
        models=(),
        constraints=(),
        authentication=(AuthRequirement("api_key", True, "sk-probe-secret"),),
    )

    with pytest.raises(ValueError, match="unsupported authentication configuration"):
        manifest.to_dict()


def test_mcp_discovery_rejects_custom_credential_shaped_authentication(monkeypatch) -> None:
    manifest = ProviderManifest(
        provider_id="custom-provider",
        display_name="Custom Provider",
        manifest_version="1.0",
        endpoint_class="test",
        capabilities=(Capability("test", "text", "Test capability."),),
        models=(),
        constraints=(),
        authentication=(AuthRequirement("api_key", True, "sk-probe-secret"),),
    )
    monkeypatch.setattr(
        capability_mcp_server,
        "_registry",
        CapabilityRegistry((manifest,)),
    )

    with pytest.raises(ValueError, match="unsupported authentication configuration"):
        capability_mcp_server.get_capability_provider("custom-provider")


def test_mcp_discovery_delegates_to_safe_registry_metadata() -> None:
    providers = list_capability_providers(modality="audio")

    assert [item["provider_id"] for item in providers] == ["elevenlabs"]
    assert get_capability_provider("elevenlabs")["authentication"] == [
        {"scheme": "api_key", "required": True, "configuration": "environment"}
    ]
    assert list_capability_models("elevenlabs")[0]["model_id"] == "eleven_multilingual_v2"