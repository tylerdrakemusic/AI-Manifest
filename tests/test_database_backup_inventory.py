from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.utils.database_backup_inventory import (
    build_backup_manifest,
    get_backupable_databases,
    load_database_inventory,
    resolve_database_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "⊕Workspace" / ".worktrees" / "feature-FR-20260816-workspace-local-database-backup"))
import src.utils  # noqa: E402
src.utils.__path__.insert(0, str(Path(__file__).resolve().parents[4] / "⊕Workspace" / ".worktrees" / "feature-FR-20260816-workspace-local-database-backup" / "src" / "utils"))
from src.utils.database_backup import (  # noqa: E402
    DatabaseBackup,
    LocalVolumeDestination,
    discover_and_validate_manifest,
    validate_recent_backups,
)


def _inventory(databases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": "ai_manifest",
        "databases": databases,
    }


def _database(**overrides: object) -> dict[str, object]:
    database: dict[str, object] = {
        "id": "manifest-todos",
        "locator": "ai_manifest/coordination-store",
        "basename": "manifest_todos.db",
        "classification": "coordination",
        "backup_allowed": True,
        "encryption": "sqlcipher",
        "key_env_var": "MANIFEST_TODOS_DB_KEY",
        "reason": "Canonical manifest coordination database.",
    }
    database.update(overrides)
    return database


def test_committed_inventory_registers_manifest_todos_without_key_material() -> None:
    project_root = Path(__file__).resolve().parent.parent
    inventory = load_database_inventory(
        project_root / "src" / "config" / "database_backup_inventory.json"
    )

    entries = inventory["databases"]
    assert entries[0]["id"] == "manifest-todos"
    assert entries[0]["backup_allowed"] is True
    assert entries[0]["encryption"] == "sqlcipher"
    assert entries[0]["key_env_var"] == "MANIFEST_TODOS_DB_KEY"
    assert "key_value" not in json.dumps(inventory).lower()
    assert "secret" not in json.dumps(inventory).lower()


def test_backup_selection_is_inventory_driven_and_default_denies_excluded_stores(
    tmp_path: Path,
) -> None:
    future_approved = _database(
        id="manifest-approved-future-store",
        locator="ai_manifest/future-store",
        basename="future_store.sqlite3",
        classification="canonical",
        backup_allowed=True,
        key_env_var="FUTURE_STORE_DB_KEY",
        reason="Explicitly approved future canonical store.",
    )
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(
        json.dumps(
            _inventory(
                [
                    _database(),
                    future_approved,
                    _database(
                        id="manifest-todos-legacy",
                        locator="ai_manifest/legacy-store",
                        basename="todos.db",
                        classification="legacy",
                        backup_allowed=False,
                        reason="Superseded coordination store.",
                    ),
                    _database(
                        id="manifest-lily-config",
                        locator="ai_manifest/lily-config-store",
                        basename="lily_config.db",
                        classification="derived",
                        backup_allowed=False,
                        reason="Generated configuration store.",
                    ),
                ]
            )
        ),
        encoding="utf-8",
    )

    inventory = load_database_inventory(inventory_path)

    assert [entry["id"] for entry in get_backupable_databases(inventory)] == [
        "manifest-todos",
        "manifest-approved-future-store",
    ]


def test_inventory_projects_approved_entries_into_generic_backup_manifest() -> None:
    manifest = build_backup_manifest(_inventory([_database()]))

    assert manifest["databases"][0]["id"] == "manifest-todos"
    assert manifest["databases"][0]["encryption"] == "sqlcipher"
    assert manifest["databases"][0]["key_env"] == "MANIFEST_TODOS_DB_KEY"
    assert manifest["databases"][0]["path"] == "ai_manifest/coordination-store"
    assert manifest["databases"][0]["discovery"] == {
        "project": "ai_manifest",
        "basename": "manifest_todos.db",
    }


def test_resolve_database_path_stays_within_project_root(tmp_path: Path) -> None:
    entry = _database()

    assert resolve_database_path(tmp_path, entry) == (
        tmp_path / "src" / "data" / "manifest_todos.db"
    )


@pytest.mark.parametrize(
    "entry",
    [
        _database(locator="../outside-store"),
        _database(encryption="sqlite"),
        _database(key_env_var="not-an-environment-variable"),
        _database(backup_allowed=True, classification="approval-required"),
    ],
)
def test_load_database_inventory_rejects_unsafe_or_denied_contract_entries(
    tmp_path: Path, entry: dict[str, object]
) -> None:
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(
        json.dumps(_inventory([entry])), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_database_inventory(inventory_path)


def test_committed_inventory_runs_shared_backup_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKSPACE_BACKUP_MANIFEST_KEY", "test-manifest-key")
    project_root = Path(__file__).resolve().parent.parent
    manifest = build_backup_manifest(load_database_inventory(project_root / "src" / "config" / "database_backup_inventory.json"))
    source_root = tmp_path / "ai_manifest"
    source = source_root / "src" / "data" / "manifest_todos.db"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"isolated-fixture")
    destination = LocalVolumeDestination(tmp_path / "external", "manifest-volume", provision=True)
    for second in (0, 1):
        DatabaseBackup(manifest, {"ai_manifest": source_root}, destination, "manifest-volume", now=lambda second=second: f"2026-08-16T12:00:0{second}Z", retention=1).run()
    assert len(list((destination.path() / "generations").iterdir())) == 1
    drift = source_root / "src" / "data" / "unexpected.db"
    drift.write_bytes(b"drift")
    with pytest.raises(ValueError, match="unregistered"):
        discover_and_validate_manifest(manifest, {"ai_manifest": source_root})
    drift.unlink()
    manifest_path = next((destination.path() / "generations").glob("*/manifest.json"))
    restore_root = tmp_path / "restore"
    DatabaseBackup.restore(manifest_path, destination, restore_root, True, "manifest-volume", allow_canonical_restore=True)
    assert (restore_root / "ai_manifest/coordination-store").read_bytes() == b"isolated-fixture"
    validate_recent_backups(destination, "manifest-volume", restore_validator=lambda *_: None)
    assert str(restore_root) not in (destination.path() / "backup-audit.jsonl").read_text(encoding="utf-8")