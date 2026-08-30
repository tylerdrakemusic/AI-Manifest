"""👁 ElevenLabs MCP Server — exposes TTS and voice tools via Model Context Protocol.

Launch: C:\\G\\python.exe mcp_server.py
Transport: stdio (VS Code / Copilot compatible)
API key: set ELEVENLABS_API_KEY in Windows System Environment Variables.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from src.utils.audio_output_policy import atomic_write_bytes, resolve_audio_output_path

# ── Load env (key expected in Windows system env via ELEVENLABS_API_KEY) ────
# No hardcoded path fallback — use Windows System Environment Variables.

# ── Logging (stderr only — stdout is MCP JSON-RPC) ──────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("elevenlabs-mcp")

# ── Constants ────────────────────────────────────────────────────
BASE_URL = "https://api.elevenlabs.io/v1"
OUTPUT_DIR = Path(r"f:\👁AI-Manifest\output\tts")

DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}

# ── API Key ──────────────────────────────────────────────────────


def _load_api_key() -> str:
    """Load ElevenLabs API key from ELEVENLABS_API_KEY env var."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY not set. Set it via: "
            "[System.Environment]::SetEnvironmentVariable('ELEVENLABS_API_KEY', 'your-key', 'Machine')"
        )
    return key.strip()


def _headers() -> dict[str, str]:
    key = _load_api_key()
    return {
        "xi-api-key": key,
        "Content-Type": "application/json",
    }


# ── FastMCP Server ───────────────────────────────────────────────
mcp = FastMCP(
    "elevenlabs",
    instructions=(
        "ElevenLabs voice synthesis server. Use text_to_speech to convert text "
        "to audio files. Use list_voices to discover available voice IDs. "
        "Use get_subscription_info to check usage quota."
    ),
)


@mcp.tool()
def list_voices() -> str:
    """List all available ElevenLabs voices.

    Returns a JSON array of voices with voice_id, name, and category.
    """
    log.info("Listing voices")
    resp = httpx.get(f"{BASE_URL}/voices", headers=_headers(), timeout=30)
    resp.raise_for_status()
    voices = resp.json().get("voices", [])
    summary = [
        {
            "voice_id": v["voice_id"],
            "name": v["name"],
            "category": v.get("category", "unknown"),
            "labels": v.get("labels", {}),
        }
        for v in voices
    ]
    return json.dumps(summary, indent=2)


@mcp.tool()
def text_to_speech(
    text: str,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    output_filename: str = "output.mp3",
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """Synthesize text to an MP3 audio file using ElevenLabs.

    Args:
        text: The text to convert to speech (max ~5000 chars recommended).
        voice_id: ElevenLabs voice ID. Default is 'Rachel'. Use list_voices to find others.
        output_filename: Filename for the output audio (saved to AI-Manifest/output/tts/).
        model_id: ElevenLabs model. Default: eleven_multilingual_v2.

    Returns:
        Path to the saved audio file and byte size.
    """
    if not text or not text.strip():
        return "Error: text cannot be empty."

    output_path = resolve_audio_output_path(
        OUTPUT_DIR,
        output_filename,
        allowed_extensions=(".mp3",),
    )

    log.info("TTS: %d chars, voice=%s, file=%s", len(text), voice_id, output_path.name)

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": DEFAULT_VOICE_SETTINGS,
    }
    resp = httpx.post(
        f"{BASE_URL}/text-to-speech/{voice_id}",
        headers=_headers(),
        json=payload,
        params={"output_format": DEFAULT_OUTPUT_FORMAT},
        timeout=60,
    )
    resp.raise_for_status()

    atomic_write_bytes(output_path, resp.content)

    return json.dumps({
        "status": "ok",
        "path": str(output_path),
        "size_bytes": len(resp.content),
        "voice_id": voice_id,
        "model_id": model_id,
        "chars": len(text),
    })


@mcp.tool()
def text_to_speech_base64(
    text: str,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """Synthesize text and return audio as base64-encoded MP3.

    Use this when you want to embed audio inline rather than saving to disk.

    Args:
        text: The text to convert to speech.
        voice_id: ElevenLabs voice ID. Default is 'Rachel'.
        model_id: ElevenLabs model ID.

    Returns:
        JSON with base64-encoded audio data and metadata.
    """
    if not text or not text.strip():
        return "Error: text cannot be empty."

    log.info("TTS-base64: %d chars, voice=%s", len(text), voice_id)

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": DEFAULT_VOICE_SETTINGS,
    }
    resp = httpx.post(
        f"{BASE_URL}/text-to-speech/{voice_id}",
        headers=_headers(),
        json=payload,
        params={"output_format": DEFAULT_OUTPUT_FORMAT},
        timeout=60,
    )
    resp.raise_for_status()

    audio_b64 = base64.b64encode(resp.content).decode("ascii")
    return json.dumps({
        "status": "ok",
        "audio_base64": audio_b64,
        "format": "mp3",
        "size_bytes": len(resp.content),
        "voice_id": voice_id,
        "chars": len(text),
    })


@mcp.tool()
def get_subscription_info() -> str:
    """Get ElevenLabs subscription info including character usage quota.

    Returns:
        JSON with tier, character count, character limit, and other plan details.
    """
    log.info("Fetching subscription info")
    resp = httpx.get(
        f"{BASE_URL}/user/subscription", headers=_headers(), timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return json.dumps({
        "tier": data.get("tier", "unknown"),
        "character_count": data.get("character_count", 0),
        "character_limit": data.get("character_limit", 0),
        "next_reset": data.get("next_character_count_reset_unix"),
        "voice_limit": data.get("voice_limit", 0),
    }, indent=2)


# ── Entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Starting ElevenLabs MCP server (stdio)")
    mcp.run(transport="stdio")
