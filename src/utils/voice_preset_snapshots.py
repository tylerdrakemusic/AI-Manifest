"""Durable immutable voice preset snapshots stored beside the TTS queue."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any, Mapping

from src.utils.tts_queue_db import get_connection


_SECRET_MARKERS = ("key", "token", "password", "secret", "credential")
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS voice_preset_snapshots (
    name         TEXT NOT NULL,
    version      INTEGER NOT NULL,
    voice_id     TEXT NOT NULL,
    intended_use TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    approved     INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0, 1)),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (name, version)
)
"""
_CREATE_IMMUTABILITY_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS prevent_voice_preset_snapshot_update
BEFORE UPDATE ON voice_preset_snapshots
BEGIN
    SELECT RAISE(ABORT, 'voice preset snapshots are immutable');
END
"""
_CREATE_DELETE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS prevent_voice_preset_snapshot_delete
BEFORE DELETE ON voice_preset_snapshots
BEGIN
    SELECT RAISE(ABORT, 'voice preset snapshots are immutable');
END
"""


@dataclass(frozen=True, slots=True)
class VoicePresetSnapshot:
    """An immutable persisted voice preset snapshot."""

    name: str
    version: int
    voice_id: str
    intended_use: str
    settings: Mapping[str, Any]
    approved: bool = False


def init_voice_preset_snapshots(connection: sqlite3.Connection) -> None:
    """Create the snapshot catalog in an existing WAL-mode database."""
    connection.execute(_CREATE_TABLE_SQL)
    connection.execute(_CREATE_IMMUTABILITY_TRIGGER_SQL)
    connection.execute(_CREATE_DELETE_TRIGGER_SQL)
    connection.commit()


def save_snapshot(
    connection: sqlite3.Connection | None = None,
    *,
    name: str,
    voice_id: str,
    intended_use: str,
    settings: Mapping[str, Any],
    approved: bool = False,
) -> VoicePresetSnapshot:
    """Append a named snapshot revision and return its immutable value."""
    _validate_snapshot(name, voice_id, intended_use, settings)
    owns_connection = connection is None
    active_connection = connection or get_connection()
    try:
        init_voice_preset_snapshots(active_connection)
        row = active_connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM voice_preset_snapshots WHERE name=?",
            (name,),
        ).fetchone()
        version = int(row[0])
        active_connection.execute(
            "INSERT INTO voice_preset_snapshots "
            "(name, version, voice_id, intended_use, settings_json, approved) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, version, voice_id, intended_use, _serialize_settings(settings), int(approved)),
        )
        active_connection.commit()
        return VoicePresetSnapshot(name, version, voice_id, intended_use, dict(settings), approved)
    finally:
        if owns_connection:
            active_connection.close()


def get_snapshot(
    connection: sqlite3.Connection | None, name: str, version: int
) -> VoicePresetSnapshot:
    """Return an exact snapshot revision or raise a deterministic ``KeyError``."""
    active_connection, owns_connection = _connection_for_lookup(connection)
    try:
        init_voice_preset_snapshots(active_connection)
        row = active_connection.execute(
            "SELECT name, version, voice_id, intended_use, settings_json, approved "
            "FROM voice_preset_snapshots WHERE name=? AND version=?",
            (name, version),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown voice preset snapshot: {name} v{version}")
        return _snapshot_from_row(row)
    finally:
        if owns_connection:
            active_connection.close()


def get_latest_snapshot(
    connection: sqlite3.Connection | None, name: str
) -> VoicePresetSnapshot:
    """Return the latest revision for a name or raise a deterministic ``KeyError``."""
    active_connection, owns_connection = _connection_for_lookup(connection)
    try:
        init_voice_preset_snapshots(active_connection)
        row = active_connection.execute(
            "SELECT name, version, voice_id, intended_use, settings_json, approved "
            "FROM voice_preset_snapshots WHERE name=? ORDER BY version DESC LIMIT 1",
            (name,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown voice preset snapshot: {name}")
        return _snapshot_from_row(row)
    finally:
        if owns_connection:
            active_connection.close()


def _connection_for_lookup(
    connection: sqlite3.Connection | None,
) -> tuple[sqlite3.Connection, bool]:
    return (connection, False) if connection is not None else (get_connection(), True)


def _validate_snapshot(
    name: str, voice_id: str, intended_use: str, settings: Mapping[str, Any]
) -> None:
    if not name.strip() or not voice_id.strip() or not intended_use.strip():
        raise ValueError("preset name, voice_id, and intended_use are required")
    if any(
        any(marker in key.lower() for marker in _SECRET_MARKERS) for key in settings
    ):
        raise ValueError("preset settings cannot contain secrets")


def _serialize_settings(settings: Mapping[str, Any]) -> str:
    return json.dumps(dict(settings), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _snapshot_from_row(row: sqlite3.Row) -> VoicePresetSnapshot:
    return VoicePresetSnapshot(
        name=row["name"],
        version=row["version"],
        voice_id=row["voice_id"],
        intended_use=row["intended_use"],
        settings=json.loads(row["settings_json"]),
        approved=bool(row["approved"]),
    )