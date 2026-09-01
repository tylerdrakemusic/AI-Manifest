from __future__ import annotations

import pytest

from src.voice_orchestration import (
    OrchestrationItem,
    VoiceAvailability,
    VoicePresetRegistry,
    orchestrate_voices,
    validate_voice_availability,
)


def test_orchestration_requires_an_approved_preset_for_its_intended_use() -> None:
    registry = VoicePresetRegistry()
    registry.register(
        name="brief-narrator",
        voice_id="voice-1",
        intended_use="executive_brief",
        settings={"stability": 0.5},
    )

    with pytest.raises(PermissionError, match="approved"):
        registry.require_approved("brief-narrator", intended_use="executive_brief")

    registry.approve("brief-narrator", intended_use="executive_brief")
    preset = registry.require_approved(
        "brief-narrator", intended_use="executive_brief"
    )

    assert preset.voice_id == "voice-1"
    assert preset.version == 1


def test_registering_a_revision_preserves_the_previous_immutable_version() -> None:
    registry = VoicePresetRegistry()
    first = registry.register(
        name="narrator",
        voice_id="voice-1",
        intended_use="brief",
        settings={"stability": 0.5},
    )
    second = registry.register(
        name="narrator",
        voice_id="voice-2",
        intended_use="brief",
        settings={"stability": 0.7},
    )

    assert first.version == 1
    assert first.voice_id == "voice-1"
    assert second.version == 2
    with pytest.raises(TypeError):
        first.settings["stability"] = 0.9


@pytest.mark.parametrize(
    "setting_name",
    ["password", "client_secret", "secret", "credential", "credentials"],
)
def test_register_rejects_secret_like_settings_without_mutating_registry(
    setting_name: str,
) -> None:
    registry = VoicePresetRegistry()

    with pytest.raises(ValueError, match="secrets"):
        registry.register(
            name="unsafe",
            voice_id="voice-1",
            intended_use="brief",
            settings={setting_name: "never-store-this"},
        )

    with pytest.raises(KeyError, match="unknown voice preset"):
        registry.require_approved("unsafe", intended_use="brief")


def test_register_preserves_legitimate_voice_settings() -> None:
    settings = {
        "stability": 0.5,
        "similarity_boost": 0.8,
        "style": 0.2,
        "use_speaker_boost": True,
    }

    preset = VoicePresetRegistry().register(
        name="safe",
        voice_id="voice-1",
        intended_use="brief",
        settings=settings,
    )

    assert dict(preset.settings) == settings


@pytest.mark.parametrize(
    ("voices", "voice_id", "expected"),
    [
        ([{"voice_id": "voice-1"}], "voice-1", VoiceAvailability.AVAILABLE),
        ([{"voice_id": "voice-2"}], "voice-1", VoiceAvailability.UNKNOWN),
        ([{"voice_id": "voice-1", "status": "deleted"}], "voice-1", VoiceAvailability.DELETED),
        ([{"voice_id": "voice-1", "status": "unavailable"}], "voice-1", VoiceAvailability.UNAVAILABLE),
    ],
)
def test_validate_voice_availability_classifies_provider_metadata(
    voices: list[dict[str, str]], voice_id: str, expected: VoiceAvailability
) -> None:
    class Client:
        def list_voices(self) -> list[dict[str, str]]:
            return voices

    assert validate_voice_availability(Client(), voice_id) is expected


def test_validate_voice_availability_explicitly_allows_local_fallback() -> None:
    class OfflineClient:
        def list_voices(self) -> list[dict[str, str]]:
            raise RuntimeError("provider unavailable")

    assert (
        validate_voice_availability(OfflineClient(), "voice-1", allow_local_fallback=True)
        is VoiceAvailability.LOCAL_FALLBACK
    )


def test_orchestration_publishes_ordered_outputs_only_after_all_renders_succeed(
    tmp_path,
) -> None:
    registry = VoicePresetRegistry()
    for name, voice_id in (("first", "voice-1"), ("second", "voice-2")):
        registry.register(
            name=name,
            voice_id=voice_id,
            intended_use="brief",
            settings={},
        )
        registry.approve(name, intended_use="brief")

    class Client:
        calls: list[str] = []

        def text_to_speech(self, text: str, voice_id: str, **kwargs: object) -> bytes:
            self.calls.append(voice_id)
            return text.encode("ascii")

    client = Client()
    result = orchestrate_voices(
        [
            OrchestrationItem("one", "first", "brief"),
            OrchestrationItem("two", "second", "brief"),
        ],
        registry=registry,
        client=client,
        output_root=tmp_path,
        output_stem="Daily Brief",
        availability=lambda _voice_id: VoiceAvailability.AVAILABLE,
    )

    assert result.complete is True
    assert client.calls == ["voice-1", "voice-2"]
    assert [path.name for path in result.output_paths] == [
        "daily-brief-01-first.mp3",
        "daily-brief-02-second.mp3",
    ]
    assert result.output_paths[0].read_bytes() == b"one"


def test_orchestration_does_not_publish_partial_completion(tmp_path) -> None:
    registry = VoicePresetRegistry()
    for name in ("first", "second"):
        registry.register(name=name, voice_id=name, intended_use="brief", settings={})
        registry.approve(name, intended_use="brief")

    class FailingClient:
        def text_to_speech(self, text: str, voice_id: str, **kwargs: object) -> bytes:
            if voice_id == "second":
                raise RuntimeError("render failed")
            return b"first-audio"

    with pytest.raises(RuntimeError, match="render failed"):
        orchestrate_voices(
            [
                OrchestrationItem("one", "first", "brief"),
                OrchestrationItem("two", "second", "brief"),
            ],
            registry=registry,
            client=FailingClient(),
            output_root=tmp_path,
            output_stem="brief",
            availability=lambda _voice_id: VoiceAvailability.AVAILABLE,
        )

    assert list(tmp_path.glob("*.mp3")) == []