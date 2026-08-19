from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskSpec:
    """Pure scheduled-task values without secret material."""

    executable: Path
    arguments: tuple[str, ...]
    trigger: str
    frequency: str
    environment_names: tuple[str, ...]


def build_task_spec(project_root: Path, python_path: Path) -> TaskSpec:
    """Build the daily AI-Manifest backup task argument contract."""
    root = Path(project_root).resolve()
    launcher = root / "tools" / "run_database_backup.ps1"
    return TaskSpec(
        executable=Path("PowerShell.exe"),
        arguments=(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            "-Python",
            str(python_path),
            "-Inventory",
            str(root / "src" / "config" / "database_backup_inventory.json"),
            "-ProjectRoot",
            str(root),
        ),
        trigger="02:00",
        frequency="DAILY",
        environment_names=(
            "WORKSPACE_BACKUP_VOLUME",
            "WORKSPACE_BACKUP_VOLUME_ID",
            "WORKSPACE_BACKUP_MANIFEST_KEY",
            "MANIFEST_TODOS_DB_KEY",
        ),
    )