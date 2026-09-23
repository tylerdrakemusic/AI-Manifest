"""Typed, provider-neutral capability registry models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


_SAFE_AUTH_CONFIGURATIONS = frozenset({"environment", "none"})


@dataclass(frozen=True)
class Capability:
    """A provider capability and its modality."""

    capability_id: str
    modality: str
    description: str


@dataclass(frozen=True)
class ModelSpec:
    """A provider model known by a repository-owned manifest."""

    model_id: str
    modalities: tuple[str, ...]
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class Constraint:
    """A safe, descriptive model or provider constraint."""

    constraint_id: str
    description: str


@dataclass(frozen=True)
class AuthRequirement:
    """Non-secret authentication metadata."""

    scheme: str
    required: bool
    configuration: str


@dataclass(frozen=True)
class ProviderManifest:
    """Versioned, safe-to-serialize provider capability metadata."""

    provider_id: str
    display_name: str
    manifest_version: str
    endpoint_class: str
    capabilities: tuple[Capability, ...]
    models: tuple[ModelSpec, ...]
    constraints: tuple[Constraint, ...]
    authentication: tuple[AuthRequirement, ...]

    def __post_init__(self) -> None:
        if not self.provider_id or not self.manifest_version:
            raise ValueError("provider_id and manifest_version are required")
        if not self.capabilities:
            raise ValueError("a provider must declare at least one capability")
        if any(field in {"health", "quota"} for field in self._field_names()):
            raise ValueError("live health and quota fields are not registry metadata")

    def _field_names(self) -> set[str]:
        return set(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        """Serialize only repository-owned, non-secret discovery metadata."""
        for requirement in self.authentication:
            if requirement.configuration not in _SAFE_AUTH_CONFIGURATIONS:
                raise ValueError("unsupported authentication configuration")
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "manifest_version": self.manifest_version,
            "endpoint_class": self.endpoint_class,
            "capabilities": [asdict(item) for item in self.capabilities],
            "models": [asdict(item) for item in self.models],
            "constraints": [asdict(item) for item in self.constraints],
            "authentication": [asdict(item) for item in self.authentication],
        }