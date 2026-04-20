"""Token loader — env-first (.env), file fallback (tokens/)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the executedcode root on first import
load_dotenv(Path(r"f:\executedcode\.env"))

TOKENS_DIR = Path(r"f:\executedcode\tokens")

# Map token file names → env var names
_ENV_MAP: dict[str, str] = {
    "elevenlabs": "ELEVENLABS_API_KEY",
    "IBM": "IBM_QUANTUM_TOKEN",
    "fb": "FB_TOKEN",
    "googleAPIKey": "GOOGLE_API_KEY",
    "openAPI": "OPENAI_API_KEY",
    "wpGetMigrationToken": "WP_MIGRATION_TOKEN",
    "perf_db_key": "PERF_DB_KEY",
}


def load_token(name: str) -> str:
    """Load an API key: check env vars first, fall back to tokens/ file."""
    env_key = _ENV_MAP.get(name)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val.strip()

    # File fallback
    token_path = TOKENS_DIR / name
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()

    raise FileNotFoundError(
        f"Token '{name}' not found in env var "
        f"{env_key or '(unmapped)'} or file {token_path}."
    )
