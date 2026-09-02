from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys

import pytest

import tools.restore_database_backup as restore_database_backup_module
from src.utils.database_backup import (
    BackupError,
    DatabaseBackup,
    DestinationIdentityError,
    LocalVolumeDestination,
    RestoreApprovalError,
    resolve_approved_source,
    validate_backup,
    validate_sqlcipher_restore,
)
import src.utils.database_backup as database_backup_module
from tools.register_database_backup_task import build_task_spec
from tools.restore_database_backup import restore_backup
from tools.run_database_backup import run_backup


def test_resolve_approved_source_ignores_worktree_and_generated_copies(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "AI-Manifest"
    canonical = project_root / "src" / "data" / "manifest_todos.db"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"canonical")

    worktree_copy = (
        project_root
        / ".worktrees"
        / "other"
        / "src"
        / "data"
        / "manifest_todos.db"
    )
    worktree_copy.parent.mkdir(parents=True)
    worktree_copy.write_bytes(b"wrong-copy")
    generated_copy = project_root / "output" / "manifest_todos.db"
    generated_copy.parent.mkdir(parents=True)
    generated_copy.write_bytes(b"wrong-copy")

    entry = {
        "id": "manifest-todos",
        "path": "ai_manifest/coordination-store",
        "discovery": {"project": "ai_manifest", "basename": "manifest_todos.db"},
        "classification": "coordination",
        "backup_allowed": True,
        "reason": "Canonical manifest coordination database.",
    }

    assert resolve_approved_source(project_root, entry) == canonical


def test_resolve_approved_source_rejects_missing_canonical_database(tmp_path: Path) -> None:
    entry = {
        "id": "manifest-todos",
        "path": "ai_manifest/coordination-store",
        "discovery": {"project": "ai_manifest", "basename": "manifest_todos.db"},
        "classification": "coordination",
        "backup_allowed": True,
        "reason": "Canonical manifest coordination database.",
    }

    with pytest.raises(BackupError, match="canonical source is missing"):
        resolve_approved_source(tmp_path, entry)


def test_shared_engine_uses_configured_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "workspace"
    engine_path = workspace_root / "src" / "utils" / "database_backup.py"
    engine_path.parent.mkdir(parents=True)
    engine_path.write_text("CONTRACT_MARKER = 'configured'\n", encoding="utf-8")
    monkeypatch.delenv("WORKSPACE_BACKUP_ENGINE_PATH", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))

    assert database_backup_module._shared_engine_path() == engine_path


def test_shared_engine_fails_closed_when_configured_contract_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WORKSPACE_BACKUP_ENGINE_PATH", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "missing-workspace"))

    with pytest.raises(
        ImportError,
        match="configured Workspace database backup contract is unavailable",
    ):
        database_backup_module._shared_engine_path()


def test_shared_engine_loads_all_workspace_utility_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "workspace"
    utilities = workspace_root / "src" / "utils"
    utilities.mkdir(parents=True)
    (utilities / "database_backup.py").write_text(
        "from src.utils.database_backup_scope import CLASSIFICATIONS\n"
        "from src.utils.database_backup_observability import enforce_retention\n"
        "CONTRACT_MARKER = (CLASSIFICATIONS, enforce_retention)\n",
        encoding="utf-8",
    )
    (utilities / "database_backup_scope.py").write_text(
        "CLASSIFICATIONS = frozenset({'coordination'})\n",
        encoding="utf-8",
    )
    (utilities / "database_backup_observability.py").write_text(
        "def enforce_retention(*args, **kwargs):\n    return []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.delenv("WORKSPACE_BACKUP_ENGINE_PATH", raising=False)
    staged_module_names = (
        "src.utils.database_backup_scope",
        "src.utils.database_backup_observability",
    )
    original_modules = {
        name: sys.modules.get(name) for name in staged_module_names
    }

    try:
        loaded_engine = database_backup_module._load_shared_engine()
    finally:
        for name, original_module in original_modules.items():
            if original_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original_module

    assert loaded_engine.CONTRACT_MARKER[0] == frozenset({"coordination"})


def _approved_entry() -> dict[str, object]:
    return {
        "id": "manifest-todos",
        "path": "ai_manifest/coordination-store",
        "discovery": {"project": "ai_manifest", "basename": "manifest_todos.db"},
        "classification": "coordination",
        "backup_allowed": True,
        "key_env": "MANIFEST_TODOS_DB_KEY",
        "reason": "Canonical manifest coordination database.",
    }


def _prepared_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    monkeypatch.setenv("WORKSPACE_BACKUP_MANIFEST_KEY", "manifest-test-key")
    project_root = tmp_path / "AI-Manifest"
    source = project_root / "src" / "data" / "manifest_todos.db"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"sqlcipher-encrypted-bytes")
    destination_root = tmp_path / "backup-volume"
    destination_root.mkdir()
    (destination_root / ".backup-volume-identity").write_text("trusted-volume\n", encoding="utf-8")
    return project_root, source, destination_root


def test_backup_publishes_authenticated_generation_with_exact_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)

    result = DatabaseBackup(
        project_root,
        LocalVolumeDestination(destination_root),
        "trusted-volume",
        now=lambda: "2026-08-16T12:00:00Z",
    ).run(_approved_entry())

    metadata = validate_backup(result.manifest_path)
    backup_file = result.manifest_path.parent / "ai_manifest" / "coordination-store"
    assert metadata["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert backup_file.read_bytes() == source.read_bytes()
    assert metadata["manifest_auth"]["algorithm"] == "HMAC-SHA256"
    assert "manifest-test-key" not in result.manifest_path.read_text(encoding="utf-8")


def test_backup_fails_closed_when_destination_marker_is_untrusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)
    (destination_root / ".backup-volume-identity").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(DestinationIdentityError):
        DatabaseBackup(
            project_root,
            LocalVolumeDestination(destination_root),
            "trusted-volume",
        ).run(_approved_entry())
    assert not (destination_root / "generations").exists()


def test_restore_requires_approval_and_preserves_byte_identity_in_isolated_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)
    destination = LocalVolumeDestination(destination_root)
    result = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:00:00Z"
    ).run(_approved_entry())
    restore_root = tmp_path / "isolated-restore"

    with pytest.raises(RestoreApprovalError):
        DatabaseBackup.restore(result.manifest_path, destination, restore_root, False, "trusted-volume")

    DatabaseBackup.restore(result.manifest_path, destination, restore_root, True, "trusted-volume")
    restored = restore_root / "ai_manifest" / "coordination-store"
    assert restored.read_bytes() == source.read_bytes()
    audit = (destination_root / "backup-audit.jsonl").read_text(encoding="utf-8")
    assert str(restore_root) not in audit
    assert str(source) not in audit
    assert '"target_id"' in audit


def test_restore_rejects_tampered_authenticated_manifest_before_copying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)
    destination = LocalVolumeDestination(destination_root)
    result = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:00:00Z"
    ).run(_approved_entry())
    metadata = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    metadata["source_sha256"] = "tampered"
    result.manifest_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(BackupError, match="manifest authentication"):
        DatabaseBackup.restore(
            result.manifest_path, destination, tmp_path / "isolated-restore", True, "trusted-volume"
        )


def test_scheduled_task_spec_has_no_secret_or_volume_identity_arguments(tmp_path: Path) -> None:
    spec = build_task_spec(tmp_path, Path(r"C:\G\python.exe"))

    argument_text = " ".join(spec.arguments)
    assert "-ProjectRoot" in spec.arguments
    assert str(tmp_path) in argument_text
    assert "WORKSPACE_BACKUP_VOLUME_ID" not in argument_text
    assert "WORKSPACE_BACKUP_MANIFEST_KEY" not in argument_text
    assert "MANIFEST_TODOS_DB_KEY" not in argument_text
    assert spec.environment_names == (
        "WORKSPACE_BACKUP_VOLUME",
        "WORKSPACE_BACKUP_VOLUME_ID",
        "WORKSPACE_BACKUP_MANIFEST_KEY",
        "MANIFEST_TODOS_DB_KEY",
    )


def test_operator_restore_entry_point_requires_explicit_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)
    destination = LocalVolumeDestination(destination_root)
    result = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:00:00Z"
    ).run(_approved_entry())
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME", str(destination_root))
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME_ID", "trusted-volume")

    with pytest.raises(RestoreApprovalError):
        restore_backup(result.manifest_path, tmp_path / "restore", operator_approved=False)


def test_runner_uses_inventory_as_authoritative_approved_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKSPACE_BACKUP_MANIFEST_KEY", "manifest-test-key")
    project_root = tmp_path / "AI-Manifest"
    source = project_root / "src" / "data" / "future_store.sqlite3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"future-encrypted-bytes")
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": "ai_manifest",
                "databases": [
                    {
                        "id": "future-store",
                        "locator": "ai_manifest/future-store",
                        "basename": "future_store.sqlite3",
                        "classification": "canonical",
                        "backup_allowed": True,
                        "encryption": "sqlcipher",
                        "key_env_var": "FUTURE_STORE_DB_KEY",
                        "reason": "Explicitly approved future store.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    destination_root = tmp_path / "backup-volume"
    destination_root.mkdir()
    (destination_root / ".backup-volume-identity").write_text(
        "trusted-volume\n", encoding="utf-8"
    )
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME_ID", "trusted-volume")

    with pytest.raises(ValueError, match="only manifest-todos is approved"):
        run_backup(project_root, inventory_path, destination_root)


def test_operator_restore_entry_point_validates_sqlcipher_after_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)
    destination = LocalVolumeDestination(destination_root)
    result = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:00:00Z"
    ).run(_approved_entry())
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME", str(destination_root))
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME_ID", "trusted-volume")
    validation_calls: list[tuple[Path, dict[str, object]]] = []

    def record_validation(restore_root: Path, metadata: dict[str, object]) -> None:
        validation_calls.append((restore_root, metadata))

    monkeypatch.setattr(
        restore_database_backup_module, "validate_sqlcipher_restore", record_validation
    )

    restore_root = tmp_path / "isolated-restore"
    restore_backup(result.manifest_path, restore_root, operator_approved=True)

    assert validation_calls == [(restore_root, validate_backup(result.manifest_path))]
    assert (restore_root / "ai_manifest" / "coordination-store").read_bytes() == source.read_bytes()


def test_retention_keeps_only_the_configured_number_of_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root, source, destination_root = _prepared_backup(tmp_path, monkeypatch)
    destination = LocalVolumeDestination(destination_root)
    first = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:00:00Z", retention=1
    ).run(_approved_entry())
    second = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:01:00Z", retention=1
    ).run(_approved_entry())

    assert first.manifest_path.parent != second.manifest_path.parent
    assert list((destination_root / "generations").iterdir()) == [second.manifest_path.parent]


def test_restored_sqlcipher_generation_reopens_with_environment_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlcipher3
    key = "sqlcipher-test-key"
    monkeypatch.setenv("WORKSPACE_BACKUP_MANIFEST_KEY", "manifest-test-key")
    monkeypatch.setenv("MANIFEST_TODOS_DB_KEY", key)
    project_root = tmp_path / "AI-Manifest"
    source = project_root / "src" / "data" / "manifest_todos.db"
    source.parent.mkdir(parents=True)
    connection = sqlcipher3.connect(str(source))
    try:
        connection.execute(f'PRAGMA key="x\'{key.encode().hex()}\'"')
        connection.execute("CREATE TABLE contract (value TEXT NOT NULL)")
        connection.execute("INSERT INTO contract VALUES ('restored')")
        connection.commit()
    finally:
        connection.close()
    destination_root = tmp_path / "backup-volume"
    destination_root.mkdir()
    (destination_root / ".backup-volume-identity").write_text("trusted-volume\n", encoding="utf-8")
    destination = LocalVolumeDestination(destination_root)
    result = DatabaseBackup(
        project_root, destination, "trusted-volume", now=lambda: "2026-08-16T12:00:00Z"
    ).run(_approved_entry())
    restore_root = tmp_path / "isolated-restore"
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME", str(destination_root))
    monkeypatch.setenv("WORKSPACE_BACKUP_VOLUME_ID", "trusted-volume")
    restore_backup(result.manifest_path, restore_root, operator_approved=True)

    metadata = validate_backup(result.manifest_path)
    assert metadata["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()