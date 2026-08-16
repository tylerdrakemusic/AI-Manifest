from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.database_backup import (
    DatabaseBackup,
    LocalVolumeDestination,
    RestoreApprovalError,
    validate_backup,
    validate_sqlcipher_restore,
)


def restore_backup(manifest_path: Path, restore_root: Path, operator_approved: bool) -> None:
    """Restore one authenticated generation using environment-backed volume identity."""
    if not operator_approved:
        raise RestoreApprovalError("restore requires explicit operator approval")
    volume_root = Path(os.environ.get("WORKSPACE_BACKUP_VOLUME", ""))
    volume_identity = os.environ.get("WORKSPACE_BACKUP_VOLUME_ID", "").strip()
    if not volume_root.is_dir() or not volume_identity:
        raise RestoreApprovalError("trusted backup volume and identity are required")
    DatabaseBackup.restore(
        manifest_path=manifest_path,
        destination=LocalVolumeDestination(volume_root),
        restore_root=restore_root,
        operator_approved=True,
        expected_destination_identity=volume_identity,
    )
    metadata = validate_backup(manifest_path)
    validate_sqlcipher_restore(restore_root, metadata)  # Validate SQLCipher after restore


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore an AI-Manifest database generation in isolation.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--restore-root", type=Path, required=True)
    parser.add_argument("--operator-approved", action="store_true")
    args = parser.parse_args()
    restore_backup(args.manifest, args.restore_root, args.operator_approved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())