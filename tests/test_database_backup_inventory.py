from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.database_backup_inventory import (
    build_backup_manifest,
    get_backupable_databases,
    load_database_inventory,
    resolve_database_path,
)


def test_ci_exports_backup_contract_and_preserves_blocking_exclusion_reporting() -> None:
    workflow = (
        Path(__file__).resolve().parent.parent / ".github" / "workflows" / "test.yml"
    ).read_text(encoding="utf-8")

    assert "WORKSPACE_BACKUP_ENGINE_PATH=${GITHUB_WORKSPACE}/workspace/src/utils/database_backup.py" in workflow
    assert "CI exclusion report: pytest will print skip reasons and summary counts" in workflow
    assert "pytest --collect-only -q -o addopts= -m \"not playwright and not live\"" in workflow
    assert "pytest -v --tb=short -rs -m \"not playwright and not live\" --junitxml=tmp/pytest-junit.xml 2>&1 | tee pytest.log" in workflow
    assert "set -o pipefail" in workflow
    assert "continue-on-error" not in workflow


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

    with pytest.raises(ValueError, match="only manifest-todos is approved"):
        get_backupable_databases(inventory)


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
