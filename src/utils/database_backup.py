from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable, Mapping


MANIFEST_KEY_ENV = "WORKSPACE_BACKUP_MANIFEST_KEY"
DATABASE_KEY_ENV = "MANIFEST_TODOS_DB_KEY"
CANONICAL_DATABASE_ID = "manifest-todos"
CANONICAL_DATABASE_NAME = "manifest_todos.db"
CANONICAL_DATABASE_PATH = "ai_manifest/coordination-store"


def _shared_engine_path() -> Path:
    configured = os.environ.get("WORKSPACE_BACKUP_ENGINE_PATH", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
    else:
        workspace_root = os.environ.get("WORKSPACE_ROOT", "").strip()
        if not workspace_root:
            raise ImportError(
                "configured Workspace database backup contract is unavailable: "
                "WORKSPACE_ROOT or WORKSPACE_BACKUP_ENGINE_PATH is required"
            )
        candidate = Path(workspace_root).expanduser() / "src" / "utils" / "database_backup.py"
    if not candidate.is_file():
        raise ImportError(
            "configured Workspace database backup contract is unavailable: "
            f"{candidate}"
        )
    return candidate.resolve()


def _load_shared_engine() -> ModuleType:
    candidate = _shared_engine_path()
    specification = importlib.util.spec_from_file_location(
        "workspace_database_backup_contract", candidate
    )
    if specification is None or specification.loader is None:
        raise ImportError(f"unable to load Workspace database backup contract: {candidate}")
    engine_root = candidate.parents[2]
    if str(engine_root) not in sys.path:
        sys.path.insert(0, str(engine_root))
    scope_path = candidate.with_name("database_backup_scope.py")
    scope_specification = importlib.util.spec_from_file_location(
        "src.utils.database_backup_scope", scope_path
    )
    if scope_specification is None or scope_specification.loader is None:
        raise ImportError(f"Workspace database backup scope is unavailable: {scope_path}")
    scope_module = importlib.util.module_from_spec(scope_specification)
    sys.modules["src.utils.database_backup_scope"] = scope_module
    scope_specification.loader.exec_module(scope_module)
    module = importlib.util.module_from_spec(specification)
    sys.modules["workspace_database_backup_contract"] = module
    specification.loader.exec_module(module)
    return module


_SHARED_ENGINE = _load_shared_engine()
BackupError = _SHARED_ENGINE.BackupError
DestinationIdentityError = _SHARED_ENGINE.DestinationIdentityError
RestoreApprovalError = _SHARED_ENGINE.RestoreApprovalError
BackupResult = _SHARED_ENGINE.BackupResult


class LocalVolumeDestination:
    """Compatibility adapter for the shared provider-neutral destination."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.shared = _SHARED_ENGINE.LocalVolumeDestination(self.root, identity="")

    def resolve_identity(self) -> str:
        return self.shared.resolve_identity()

    def is_verified(self, expected_identity: str) -> bool:
        return self.shared.is_verified(expected_identity)

    def path(self) -> Path:
        return self.root


def _inventory_manifest(entry: Mapping[str, Any]) -> dict[str, Any]:
    _validate_canonical_entry(entry)
    discovery = entry.get("discovery")
    if not isinstance(discovery, Mapping):
        raise BackupError("approved database entry requires discovery metadata")
    return {
        "schema_version": 1,
        "fr": "FR-20260816-ai-manifest-database-backup-restore",
        "policy_status": "reviewed",
        "purpose": "AI-Manifest approved database backup.",
        "content_boundary": "Encrypted database files only.",
        "classifications": sorted(sys.modules["src.utils.database_backup_scope"].CLASSIFICATIONS),
        "databases": [{
            "id": entry["id"],
            "path": entry["path"],
            "classification": entry["classification"],
            "backup_allowed": entry["backup_allowed"],
            "reason": entry["reason"],
            "discovery": dict(discovery),
            "encryption": entry.get("encryption", "sqlcipher"),
            "key_env": entry.get("key_env", entry.get("key_env_var", DATABASE_KEY_ENV)),
        }],
        "exclusions": [],
        "not_implemented": [],
        "separate_todos": [],
    }


def resolve_approved_source(project_root: Path, entry: Mapping[str, Any]) -> Path:
    """Resolve an approved inventory source beneath the project data root."""
    _validate_canonical_entry(entry)
    if not entry.get("backup_allowed"):
        raise BackupError("database entry is not an approved source")
    discovery = entry.get("discovery")
    basename = discovery.get("basename") if isinstance(discovery, Mapping) else entry.get("basename")
    if not isinstance(basename, str) or Path(basename).name != basename:
        raise BackupError("approved source basename is invalid")
    root = Path(project_root).resolve()
    source = (root / "src" / "data" / basename).resolve()
    if root not in source.parents or not source.is_file():
        label = "canonical source" if basename == CANONICAL_DATABASE_NAME else "approved source"
        raise BackupError(f"{label} is missing: {source}")
    return source


def _validate_canonical_entry(entry: Mapping[str, Any]) -> None:
    discovery = entry.get("discovery")
    basename = discovery.get("basename") if isinstance(discovery, Mapping) else entry.get("basename")
    if (
        entry.get("id") != CANONICAL_DATABASE_ID
        or entry.get("path") != CANONICAL_DATABASE_PATH
        or basename != CANONICAL_DATABASE_NAME
    ):
        raise BackupError("only manifest-todos is approved for AI-Manifest backup")


def run_manifest_backup(
    manifest: Mapping[str, Any],
    project_root: Path,
    destination: LocalVolumeDestination,
    expected_destination_identity: str,
    now: Callable[[], str] | None = None,
    retention: int = 30,
) -> BackupResult:
    """Run the shared lifecycle for an inventory-projected manifest."""
    engine = _SHARED_ENGINE.DatabaseBackup(
        manifest=dict(manifest),
        source_root={"ai_manifest": Path(project_root)},
        destination=destination.shared,
        expected_destination_identity=expected_destination_identity,
        now=now,
        retention=retention,
    )
    return engine.run()


def validate_backup(manifest_path: Path) -> dict[str, Any]:
    """Validate a shared generation and return its authenticated metadata."""
    _SHARED_ENGINE.validate_backup(manifest_path)
    metadata = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    files = metadata.get("files", [])
    if len(files) == 1 and isinstance(files[0], Mapping):
        metadata["source_sha256"] = files[0].get("sha256")
    return metadata


class DatabaseBackup:
    """Compatibility facade that delegates lifecycle work to the shared engine."""

    def __init__(
        self,
        project_root: Path,
        destination: LocalVolumeDestination,
        expected_destination_identity: str,
        now: Callable[[], str] | None = None,
        retention: int = 30,
    ) -> None:
        self.project_root = Path(project_root)
        self.destination = destination
        self.identity = expected_destination_identity
        self.now = now
        self.retention = retention

    def run(self, entry: Mapping[str, Any]) -> BackupResult:
        return run_manifest_backup(
            _inventory_manifest(entry), self.project_root, self.destination,
            self.identity, self.now, self.retention,
        )

    @staticmethod
    def restore(
        manifest_path: Path,
        destination: LocalVolumeDestination,
        restore_root: Path,
        operator_approved: bool,
        expected_destination_identity: str,
    ) -> None:
        _SHARED_ENGINE.DatabaseBackup.restore(
            manifest_path, destination.shared, restore_root, operator_approved,
            expected_destination_identity, allow_canonical_restore=True,
        )


def validate_sqlcipher_restore(restore_root: Path, manifest: Mapping[str, Any]) -> None:
    """Reopen restored SQLCipher files through the shared validator."""
    _SHARED_ENGINE._validate_restored_databases(Path(restore_root), dict(manifest))
