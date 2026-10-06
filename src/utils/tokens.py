"""Environment-only token loader."""

import os

# Map token names to environment variable names.
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
    """Load an API key from its mapped environment variable."""
    env_key = _ENV_MAP.get(name)
    if env_key is None:
        raise FileNotFoundError(f"Token '{name}' has no environment variable mapping.")

    value = os.environ.get(env_key)
    if value:
        return value.strip()

    raise FileNotFoundError(f"Token '{name}' not found in environment variable {env_key}.")
