from __future__ import annotations

import sqlite3

import pytest

from src.utils.voice_preset_snapshots import (
    get_latest_snapshot,
    get_snapshot,
    init_voice_preset_snapshots,
    save_snapshot,
)


def _connection(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    init_voice_preset_snapshots(connection)
    return connection


def test_snapshots_persist_across_connections_and_revisions_are_immutable(tmp_path) -> None:
    database = str(tmp_path / "manifest_todos.db")
    first_connection = _connection(database)
    first = save_snapshot(
        first_connection,
        name="brief-narrator",
        voice_id="voice-1",
        intended_use="executive_brief",
        settings={"stability": 0.5},
        approved=True,
    )
    second = save_snapshot(
        first_connection,
        name="brief-narrator",
        voice_id="voice-2",
        intended_use="executive_brief",
        settings={"stability": 0.7},
    )
    first_connection.close()

    second_connection = _connection(database)
    assert first.version == 1
    assert second.version == 2
    assert get_snapshot(second_connection, "brief-narrator", 1).voice_id == "voice-1"
    assert get_latest_snapshot(second_connection, "brief-narrator").voice_id == "voice-2"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        second_connection.execute(
            "UPDATE voice_preset_snapshots SET voice_id='mutated' "
            "WHERE name='brief-narrator' AND version=1"
        )
    with pytest.raises(KeyError, match="unknown voice preset snapshot"):
        get_snapshot(second_connection, "missing", 1)
    with pytest.raises(KeyError, match="unknown voice preset snapshot"):
        get_snapshot(second_connection, "brief-narrator", 3)
    second_connection.close()


@pytest.mark.parametrize("setting_name", ["password", "client_secret", "secret", "credential", "credentials"])
def test_snapshot_rejects_secret_like_settings_without_mutating_catalog(
    tmp_path, setting_name: str
) -> None:
    connection = _connection(str(tmp_path / "manifest_todos.db"))

    with pytest.raises(ValueError, match="secrets"):
        save_snapshot(
            connection,
            name="unsafe",
            voice_id="voice-1",
            intended_use="brief",
            settings={setting_name: "never-store-this"},
        )

    with pytest.raises(KeyError, match="unknown voice preset snapshot"):
        get_latest_snapshot(connection, "unsafe")