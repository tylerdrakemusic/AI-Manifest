"""Helper for reading and updating Lily's portrait prompts from lily_config.db.

Provides two public functions:
    get_active_prompt()    -> (positive_prompt, negative_prompt | None)
    update_active_prompt() -> None

The DB is created by tools/lily/seed_lily_config.py.  This module is import-safe
even if the DB does not yet exist — callers should catch RuntimeError.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "lily_config.db"


def _connect() -> sqlite3.Connection:
    """Open a connection to lily_config.db (open/close per call for thread safety)."""
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_active_prompt() -> tuple[str, str | None]:
    """Return (positive_prompt, negative_prompt) from the active lily_prompts row.

    Parameters
    ----------
    None

    Returns
    -------
    tuple[str, str | None]
        (positive_prompt, negative_prompt).  ``negative_prompt`` may be None.

    Raises
    ------
    RuntimeError
        If the DB does not exist or no active row is present.
    """
    if not _DB_PATH.exists():
        raise RuntimeError(
            f"lily_config.db not found at {_DB_PATH}. "
            "Run tools/lily/seed_lily_config.py to initialise."
        )
    with _connect() as conn:
        row = conn.execute(
            "SELECT positive_prompt, negative_prompt "
            "FROM lily_prompts WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("No active prompt row found in lily_config.db")
    return str(row["positive_prompt"]), (row["negative_prompt"] or None)


def update_active_prompt(positive_prompt: str) -> None:
    """Update the active row's positive_prompt and refresh updated_at.

    Parameters
    ----------
    positive_prompt:
        The new positive prompt text to store.

    Raises
    ------
    RuntimeError
        If the DB does not exist.
    """
    if not _DB_PATH.exists():
        raise RuntimeError(
            f"lily_config.db not found at {_DB_PATH}. "
            "Run tools/lily/seed_lily_config.py to initialise."
        )
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE lily_prompts SET positive_prompt = ?, updated_at = ? WHERE is_active = 1",
            (positive_prompt, updated_at),
        )
        conn.commit()
