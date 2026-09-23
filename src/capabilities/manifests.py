"""Repository-owned provider capability manifests."""

from __future__ import annotations

from .models import AuthRequirement, Capability, Constraint, ModelSpec, ProviderManifest

_IMAGE = Capability("image_generation", "image", "Generate images through a provider adapter.")
_VOICE = Capability("voice_synthesis", "audio", "Synthesize speech through a provider adapter.")
_IMAGE_CONSTRAINT = Constraint("prompt_required", "A text prompt is required by the adapter.")

MANIFESTS = (
    ProviderManifest(
        provider_id="dall-e-3",
        display_name="DALL-E 3",
        manifest_version="1.0",
        endpoint_class="image_generation",
        capabilities=(_IMAGE,),
        models=(ModelSpec("dall-e-3", ("image",), ("prompt_required",)),),
        constraints=(_IMAGE_CONSTRAINT,),
        authentication=(AuthRequirement("api_key", True, "environment"),),
    ),
    ProviderManifest(
        provider_id="elevenlabs",
        display_name="ElevenLabs",
        manifest_version="1.0",
        endpoint_class="audio_generation",
        capabilities=(_VOICE,),
        models=(ModelSpec("eleven_multilingual_v2", ("audio",)),),
        constraints=(),
        authentication=(AuthRequirement("api_key", True, "environment"),),
    ),
    ProviderManifest(
        provider_id="hugging-face",
        display_name="Hugging Face",
        manifest_version="1.0",
        endpoint_class="image_generation",
        capabilities=(_IMAGE,),
        models=(ModelSpec("black-forest-labs/FLUX.1-schnell", ("image",), ("prompt_required",)),),
        constraints=(_IMAGE_CONSTRAINT,),
        authentication=(AuthRequirement("api_key", True, "environment"),),
    ),
    ProviderManifest(
        provider_id="pollinations",
        display_name="Pollinations",
        manifest_version="1.0",
        endpoint_class="image_generation",
        capabilities=(_IMAGE,),
        models=(ModelSpec("pollinations-default", ("image",), ("prompt_required",)),),
        constraints=(_IMAGE_CONSTRAINT,),
        authentication=(AuthRequirement("none", False, "none"),),
    ),
)