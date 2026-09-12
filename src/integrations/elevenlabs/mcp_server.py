"""👁 ElevenLabs MCP Server — exposes TTS and voice tools via Model Context Protocol.

Launch: C:\\G\\python.exe mcp_server.py
Transport: stdio (VS Code / Copilot compatible)
API key: set ELEVENLABS_API_KEY in Windows System Environment Variables.
"""

from __future__ import annotations

import base64
import atexit
import ctypes
from dataclasses import asdict
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.audio_output_policy import atomic_write_bytes, resolve_audio_output_path
from src.services import governed_repository_voice
from src.services.streaming_tts import StreamingTtsService

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
IS_WINDOWS_PLATFORM = os.name == "nt"
SUPPORTED_PLAYBACK_EXTENSIONS = (".mp3",)
MAX_AUDIO_FILE_BYTES = 25 * 1024 * 1024
MAX_AUDIO_DURATION_SECONDS = 120.0

DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}

REPOSITORY_VOICE_CAPABILITY = "repository_voice"

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
        "ElevenLabs voice synthesis server. Use text_to_speech to generate an "
        "audio artifact, play_audio_file to synchronously play one governed MP3 "
        "from output/tts, and submit_repository_voice to enqueue an authorized "
        "repository voice notification. Use start_streaming_tts for bounded local "
        "PCM playback, streaming_tts_status for telemetry, and "
        "cancel_streaming_tts to stop it. Use list_voices to discover voice IDs "
        "and get_subscription_info to check usage quota."
    ),
)
STREAMING_TTS_SERVICE = StreamingTtsService()


def _shutdown_streaming_tts() -> None:
    """Cancel local streaming work when the stdio server exits."""
    STREAMING_TTS_SERVICE.shutdown()


atexit.register(_shutdown_streaming_tts)


def _playback_alias(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    return f"mcp_audio_{digest}"


def _winmm() -> object:
    if not IS_WINDOWS_PLATFORM:
        raise OSError("Synchronous audio playback is only available on Windows")
    return ctypes.windll.winmm


def get_audio_duration_seconds(path: Path) -> float:
    """Read an audio duration through the native Windows multimedia API."""
    winmm = _winmm()
    alias = _playback_alias(path)
    command_buffer = ctypes.create_unicode_buffer(256)
    opened = False
    try:
        error = winmm.mciSendStringW(  # type: ignore[attr-defined]
            f'open "{path}" type mpegvideo alias {alias}',
            command_buffer,
            len(command_buffer),
            0,
        )
        if error:
            raise OSError(f"Windows multimedia open failed: {error}")
        opened = True
        error = winmm.mciSendStringW(  # type: ignore[attr-defined]
            f"status {alias} length",
            command_buffer,
            len(command_buffer),
            0,
        )
        if error:
            raise OSError(f"Windows multimedia duration lookup failed: {error}")
        return float(command_buffer.value) / 1000.0
    finally:
        if opened:
            winmm.mciSendStringW(  # type: ignore[attr-defined]
                f"close {alias}", command_buffer, len(command_buffer), 0
            )


def play_audio_path(path: Path) -> None:
    """Play an already-validated audio path synchronously through MCI."""
    winmm = _winmm()
    alias = _playback_alias(path)
    command_buffer = ctypes.create_unicode_buffer(256)
    opened = False
    try:
        error = winmm.mciSendStringW(  # type: ignore[attr-defined]
            f'open "{path}" type mpegvideo alias {alias}',
            command_buffer,
            len(command_buffer),
            0,
        )
        if error:
            raise OSError(f"Windows multimedia open failed: {error}")
        opened = True
        error = winmm.mciSendStringW(  # type: ignore[attr-defined]
            f"play {alias} wait",
            command_buffer,
            len(command_buffer),
            0,
        )
        if error:
            raise OSError(f"Windows multimedia playback failed: {error}")
    finally:
        if opened:
            winmm.mciSendStringW(  # type: ignore[attr-defined]
                f"close {alias}", command_buffer, len(command_buffer), 0
            )


@mcp.tool()
def play_audio_file(filename: str) -> dict[str, object]:
    """Synchronously play a generated MP3 from the governed output/tts directory."""
    audio_path = resolve_audio_output_path(
        OUTPUT_DIR,
        filename,
        allowed_extensions=SUPPORTED_PLAYBACK_EXTENSIONS,
    )
    if not audio_path.is_file():
        raise FileNotFoundError(filename)
    file_size = audio_path.stat().st_size
    if file_size > MAX_AUDIO_FILE_BYTES:
        raise ValueError(f"audio file size exceeds {MAX_AUDIO_FILE_BYTES} bytes")
    duration_seconds = get_audio_duration_seconds(audio_path)
    if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
        raise ValueError(
            f"audio duration exceeds {MAX_AUDIO_DURATION_SECONDS:g} seconds"
        )
    play_audio_path(audio_path)
    return {
        "status": "completed",
        "filename": filename,
        "size_bytes": file_size,
        "duration_seconds": duration_seconds,
    }


def _repository_voice_unavailable_reason() -> str | None:
    """Return a safe dependency error without contacting the provider."""
    if not callable(governed_repository_voice.submit_repository_voice):
        return "submission service unavailable"
    if not callable(governed_repository_voice.enqueue_with_status):
        return "queue unavailable"
    return None


@mcp.tool()
def submit_repository_voice(
    decision_id: str,
    text: str,
    voice_id: str,
    model_id: str = DEFAULT_MODEL_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    priority: int = 5,
    max_retries: int = 3,
) -> dict[str, object]:
    """Queue a governed repository-voice notification without provider access."""
    result = governed_repository_voice.submit_repository_voice(
        decision_id,
        text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
        priority=priority,
        max_retries=max_retries,
    )
    return asdict(result)


@mcp.tool()
def repository_voice_status() -> dict[str, object]:
    """Report governed repository-voice registration and queue availability."""
    reason = _repository_voice_unavailable_reason()
    if reason is not None:
        return {
            "capability": REPOSITORY_VOICE_CAPABILITY,
            "status": "unavailable",
            "reason": reason,
            "transport": "durable_tts_queue",
            "provider_access": "worker_only",
            "credentials_exposed": False,
        }
    return {
        "capability": REPOSITORY_VOICE_CAPABILITY,
        "status": "healthy",
        "transport": "durable_tts_queue",
        "provider_access": "worker_only",
        "credentials_exposed": False,
    }


@mcp.tool()
def start_streaming_tts(
    text: str,
    voice_id: str,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict[str, object]:
    """Start bounded local PCM playback and return an opaque session ID."""
    return STREAMING_TTS_SERVICE.start(text, voice_id, model_id)


@mcp.tool()
def streaming_tts_status(session_id: str) -> dict[str, object]:
    """Return current or retained terminal telemetry for a streaming session."""
    return STREAMING_TTS_SERVICE.status(session_id)


@mcp.tool()
def cancel_streaming_tts(session_id: str) -> dict[str, object]:
    """Cancel a streaming session and abort local playback."""
    return STREAMING_TTS_SERVICE.cancel(session_id)


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
    """Generate an MP3 artifact with ElevenLabs under the governed output/tts directory.

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
    try:
        mcp.run(transport="stdio")
    finally:
        _shutdown_streaming_tts()
