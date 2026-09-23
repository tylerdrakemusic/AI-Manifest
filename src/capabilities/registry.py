"""Deterministic offline provider capability discovery."""

from __future__ import annotations

from collections.abc import Iterable

from .manifests import MANIFESTS
from .models import ProviderManifest


class CapabilityRegistry:
    """Discover repository-owned provider manifests without network access."""

    def __init__(self, manifests: Iterable[ProviderManifest] = MANIFESTS) -> None:
        self._manifests = tuple(sorted(manifests, key=lambda item: item.provider_id))
        provider_ids = [item.provider_id for item in self._manifests]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("provider IDs must be unique")

    def list_providers(
        self,
        *,
        capability: str | None = None,
        modality: str | None = None,
    ) -> tuple[ProviderManifest, ...]:
        """List providers matching optional capability or modality filters."""
        if capability is not None and not capability.strip():
            raise ValueError("capability filter cannot be empty")
        if modality is not None and not modality.strip():
            raise ValueError("modality filter cannot be empty")
        return tuple(
            provider
            for provider in self._manifests
            if (capability is None or any(item.capability_id == capability for item in provider.capabilities))
            and (modality is None or any(modality in item.modalities for item in provider.models))
        )

    def get_provider(self, provider_id: str) -> ProviderManifest:
        """Return one provider or raise a deterministic not-found error."""
        for provider in self._manifests:
            if provider.provider_id == provider_id:
                return provider
        raise KeyError(f"provider not found: {provider_id}")

    def list_models(self, provider_id: str) -> tuple[dict[str, object], ...]:
        """Return safe model metadata for one provider."""
        return tuple(
            {
                "model_id": model.model_id,
                "modalities": list(model.modalities),
                "constraints": list(model.constraints),
            }
            for model in self.get_provider(provider_id).models
        )