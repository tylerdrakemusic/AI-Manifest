from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.database_backup_inventory import (
    get_backupable_databases,
    load_database_inventory,
    resolve_database_path,
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
        "path": "src/data/manifest_todos.db",
        "classification": "coordination",
        "backup_allowed": True,
        "encryption": "sqlcipher",
        "key_env": "MANIFEST_TODOS_DB_KEY",
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
    assert entries[0]["key_env"] == "MANIFEST_TODOS_DB_KEY"
    assert "key_value" not in json.dumps(inventory).lower()
    assert "secret" not in json.dumps(inventory).lower()


def test_backup_selection_is_inventory_driven_and_default_denies_excluded_stores(
    tmp_path: Path,
) -> None:
    future_approved = _database(
        id="manifest-approved-future-store",
        path="src/data/future_store.sqlite3",
        classification="canonical",
        backup_allowed=True,
        key_env="FUTURE_STORE_DB_KEY",
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
                        path="src/data/todos.db",
                        classification="legacy",
                        backup_allowed=False,
                        reason="Superseded coordination store.",
                    ),
                    _database(
                        id="manifest-lily-config",
                        path="src/data/lily_config.db",
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


def test_resolve_database_path_stays_within_project_root(tmp_path: Path) -> None:
    entry = _database()

    assert resolve_database_path(tmp_path, entry) == (
        tmp_path / "src" / "data" / "manifest_todos.db"
    )


@pytest.mark.parametrize(
    "entry",
    [
        _database(path="../../outside.db"),
        _database(encryption="sqlite"),
        _database(key_env="not-an-environment-variable"),
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