"""Tests for src/utils/lily_config_db.py — isolated tmp DB, no shared state."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Bootstrap project root
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import src.utils.lily_config_db as _db_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS lily_prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    positive_prompt TEXT    NOT NULL,
    negative_prompt TEXT,
    is_active       INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL
);
"""


def _make_db(tmp_path: Path, positive: str = "test positive", negative: str | None = "test negative") -> Path:
    """Create a fresh lily_config.db in tmp_path with one active row."""
    db_path = tmp_path / "lily_config.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE)
    conn.execute(
        "INSERT INTO lily_prompts (positive_prompt, negative_prompt, is_active, updated_at) VALUES (?, ?, 1, ?)",
        (positive, negative, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# get_active_prompt — happy path
# ---------------------------------------------------------------------------

def test_get_active_prompt_returns_seeded_prompts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _make_db(tmp_path, positive="my positive", negative="my negative")
    monkeypatch.setattr(_db_mod, "_DB_PATH", db_path)

    pos, neg = _db_mod.get_active_prompt()

    assert pos == "my positive"
    assert neg == "my negative"


def test_get_active_prompt_negative_none_when_null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _make_db(tmp_path, positive="positive only", negative=None)
    monkeypatch.setattr(_db_mod, "_DB_PATH", db_path)

    pos, neg = _db_mod.get_active_prompt()

    assert pos == "positive only"
    assert neg is None


# ---------------------------------------------------------------------------
# get_active_prompt — error cases
# ---------------------------------------------------------------------------

def test_get_active_prompt_raises_when_db_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "does_not_exist.db"
    monkeypatch.setattr(_db_mod, "_DB_PATH", missing)

    with pytest.raises(RuntimeError, match="lily_config.db not found"):
        _db_mod.get_active_prompt()


def test_get_active_prompt_raises_when_no_active_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "lily_config.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE)
    # Insert an INACTIVE row — no active row
    conn.execute(
        "INSERT INTO lily_prompts (positive_prompt, negative_prompt, is_active, updated_at) VALUES (?, ?, 0, ?)",
        ("inactive prompt", None, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(_db_mod, "_DB_PATH", db_path)

    with pytest.raises(RuntimeError, match="No active prompt row"):
        _db_mod.get_active_prompt()


# ---------------------------------------------------------------------------
# update_active_prompt — happy path
# ---------------------------------------------------------------------------

def test_update_active_prompt_changes_positive_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _make_db(tmp_path, positive="original prompt")
    monkeypatch.setattr(_db_mod, "_DB_PATH", db_path)

    _db_mod.update_active_prompt("updated prompt")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT positive_prompt FROM lily_prompts WHERE is_active = 1"
    ).fetchone()
    conn.close()
    assert row["positive_prompt"] == "updated prompt"


def test_update_active_prompt_refreshes_updated_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_ts = "2020-01-01T00:00:00+00:00"
    db_path = tmp_path / "lily_config.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE)
    conn.execute(
        "INSERT INTO lily_prompts (positive_prompt, negative_prompt, is_active, updated_at) VALUES (?, ?, 1, ?)",
        ("old prompt", None, old_ts),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(_db_mod, "_DB_PATH", db_path)

    _db_mod.update_active_prompt("new prompt")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT updated_at FROM lily_prompts WHERE is_active = 1").fetchone()
    conn.close()
    assert row["updated_at"] != old_ts


# ---------------------------------------------------------------------------
# update_active_prompt — error case
# ---------------------------------------------------------------------------

def test_update_active_prompt_raises_when_db_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "does_not_exist.db"
    monkeypatch.setattr(_db_mod, "_DB_PATH", missing)

    with pytest.raises(RuntimeError, match="lily_config.db not found"):
        _db_mod.update_active_prompt("anything")


# ---------------------------------------------------------------------------
# Round-trip: update then get returns new value
# ---------------------------------------------------------------------------

def test_round_trip_update_then_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _make_db(tmp_path, positive="initial value", negative="neg")
    monkeypatch.setattr(_db_mod, "_DB_PATH", db_path)

    _db_mod.update_active_prompt("round-trip new prompt")
    pos, neg = _db_mod.get_active_prompt()

    assert pos == "round-trip new prompt"
    assert neg == "neg"  # negative_prompt unchanged
