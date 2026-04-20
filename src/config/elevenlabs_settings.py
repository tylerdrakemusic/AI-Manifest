"""ElevenLabs voice synthesis settings."""

# Default voice model
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# Default voice settings
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}

# Audio output format
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

# Streaming chunk size (bytes)
STREAM_CHUNK_SIZE = 4096
