"""Governed voice presets and ordered ElevenLabs rendering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from src.integrations.elevenlabs.client import ElevenLabsClient
from src.utils.audio_output_policy import atomic_write_bytes, resolve_audio_output_path


class VoiceAvailability(StrEnum):
    """Provider state for a preset voice."""

    AVAILABLE = "available"
    UNKNOWN = "unknown"
    DELETED = "deleted"
    UNAVAILABLE = "unavailable"
    LOCAL_FALLBACK = "local_fallback"


@dataclass(frozen=True, slots=True)
class VoicePreset:
    """An immutable, non-secret voice configuration version."""

    name: str
    version: int
    voice_id: str
    intended_use: str
    settings: Mapping[str, Any]
    approved: bool = False


class VoicePresetRegistry:
    """Store versioned presets and explicit intended-use approvals."""

    def __init__(self) -> None:
        self._presets: dict[str, list[VoicePreset]] = {}

    def register(
        self,
        *,
        name: str,
        voice_id: str,
        intended_use: str,
        settings: Mapping[str, Any],
    ) -> VoicePreset:
        if not name.strip() or not voice_id.strip() or not intended_use.strip():
            raise ValueError("preset name, voice_id, and intended_use are required")
        secret_markers = ("key", "token", "password", "secret", "credential")
        if any(any(marker in key.lower() for marker in secret_markers) for key in settings):
            raise ValueError("preset settings cannot contain secrets")
        versions = self._presets.setdefault(name, [])
        preset = VoicePreset(
            name=name,
            version=len(versions) + 1,
            voice_id=voice_id,
            intended_use=intended_use,
            settings=MappingProxyType(dict(settings)),
        )
        versions.append(preset)
        return preset

    def approve(self, name: str, *, intended_use: str) -> VoicePreset:
        preset = self._latest(name)
        if preset.intended_use != intended_use:
            raise PermissionError("preset is not approved for this intended use")
        approved = VoicePreset(
            name=preset.name,
            version=preset.version,
            voice_id=preset.voice_id,
            intended_use=preset.intended_use,
            settings=preset.settings,
            approved=True,
        )
        self._presets[name][-1] = approved
        return approved

    def require_approved(self, name: str, *, intended_use: str) -> VoicePreset:
        preset = self._latest(name)
        if not preset.approved or preset.intended_use != intended_use:
            raise PermissionError("preset must be approved for its intended use")
        return preset

    def _latest(self, name: str) -> VoicePreset:
        try:
            return self._presets[name][-1]
        except (KeyError, IndexError) as exc:
            raise KeyError(f"unknown voice preset: {name}") from exc


def validate_voice_availability(
    client: ElevenLabsClient,
    voice_id: str,
    *,
    allow_local_fallback: bool = False,
) -> VoiceAvailability:
    """Classify a voice using only provider metadata and explicit fallback policy."""
    try:
        voices = client.list_voices()
    except Exception as exc:
        if getattr(exc, "response", None) is not None and exc.response.status_code == 404:
            return VoiceAvailability.DELETED
        return (
            VoiceAvailability.LOCAL_FALLBACK
            if allow_local_fallback
            else VoiceAvailability.UNAVAILABLE
        )
    matching = next((voice for voice in voices if voice.get("voice_id") == voice_id), None)
    if matching is None:
        return VoiceAvailability.UNKNOWN
    if matching.get("available") is False or matching.get("status") in {
        "deleted",
        "unavailable",
    }:
        return VoiceAvailability.DELETED if matching.get("status") == "deleted" else VoiceAvailability.UNAVAILABLE
    return VoiceAvailability.AVAILABLE


@dataclass(frozen=True, slots=True)
class OrchestrationItem:
    """One ordered text render in an orchestration request."""

    text: str
    preset_name: str
    intended_use: str


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Published result for a fully completed orchestration."""

    output_paths: tuple[Path, ...]
    complete: bool


def orchestrate_voices(
    items: Sequence[OrchestrationItem],
    *,
    registry: VoicePresetRegistry,
    client: ElevenLabsClient,
    output_root: Path | str,
    output_stem: str,
    availability: Callable[[str], VoiceAvailability] | None = None,
) -> OrchestrationResult:
    """Render items in order and publish all files only after every render succeeds."""
    if not items:
        raise ValueError("orchestration requires at least one item")
    root = Path(output_root).resolve()
    output_paths: list[Path] = []
    with TemporaryDirectory(dir=root) as staging_name:
        staging = Path(staging_name)
        staged: list[tuple[Path, Path]] = []
        for index, item in enumerate(items, start=1):
            preset = registry.require_approved(item.preset_name, intended_use=item.intended_use)
            state = (availability or (lambda voice_id: validate_voice_availability(client, voice_id)))(preset.voice_id)
            if state is not VoiceAvailability.AVAILABLE:
                raise RuntimeError(f"voice {preset.voice_id} is {state.value}")
            audio = client.text_to_speech(item.text, preset.voice_id, voice_settings=dict(preset.settings))
            filename = f"{_slug(output_stem)}-{index:02d}-{_slug(item.preset_name)}.mp3"
            staged_path = resolve_audio_output_path(staging, filename, allowed_extensions=(".mp3",))
            atomic_write_bytes(staged_path, audio)
            staged.append((staged_path, root / filename))
        for staged_path, destination in staged:
            destination = resolve_audio_output_path(root, destination.name, allowed_extensions=(".mp3",))
            atomic_write_bytes(destination, staged_path.read_bytes())
            output_paths.append(destination)
    return OrchestrationResult(output_paths=tuple(output_paths), complete=True)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    if not slug:
        raise ValueError("output names must contain alphanumeric characters")
    return slug


__all__ = [
    "OrchestrationItem",
    "OrchestrationResult",
    "VoiceAvailability",
    "VoicePreset",
    "VoicePresetRegistry",
    "orchestrate_voices",
    "validate_voice_availability",
]