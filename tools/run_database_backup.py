from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.database_backup import (
    DestinationIdentityError,
    LocalVolumeDestination,
    run_manifest_backup,
)
from src.utils.database_backup_inventory import (
    build_backup_manifest,
    get_backupable_databases,
    load_database_inventory,
)


def run_backup(project_root: Path, inventory_path: Path, volume_root: Path) -> Path:
    """Run the approved AI-Manifest backup using environment-backed identities."""
    inventory = load_database_inventory(inventory_path)
    approved = get_backupable_databases(inventory)
    if not approved:
        raise ValueError("AI-Manifest backup scope must contain an approved database")
    identity = os.environ.get("WORKSPACE_BACKUP_VOLUME_ID", "").strip()
    if not volume_root.is_dir() or not identity:
        raise DestinationIdentityError("backup volume and identity are required")
    result = run_manifest_backup(
        build_backup_manifest({**inventory, "databases": approved}),
        project_root=project_root,
        destination=LocalVolumeDestination(volume_root),
        expected_destination_identity=identity,
    )
    return result.manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AI-Manifest local database backup.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--volume-root", type=Path, required=True)
    args = parser.parse_args()
    print(run_backup(args.project_root, args.inventory, args.volume_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())