"""Shared policy for safe audio artifact paths."""

from __future__ import annotations

import ntpath
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable


def resolve_audio_output_path(
    output_root: Path | str,
    output_name: str,
    *,
    allowed_extensions: Iterable[str],
) -> Path:
    """Validate an audio name and resolve it beneath an output root."""
    if not isinstance(output_name, str) or not output_name.strip():
        raise ValueError("audio output name must be non-empty")
    if any(ord(character) < 32 or ord(character) == 127 for character in output_name):
        raise ValueError("audio output name contains control characters")
    if "/" in output_name or "\\" in output_name:
        raise ValueError("audio output name cannot contain path separators")
    if any(component == ".." for component in Path(output_name).parts):
        raise ValueError("audio output name cannot contain parent components")
    if Path(output_name).is_absolute() or ntpath.isabs(output_name):
        raise ValueError("audio output name cannot be absolute")

    extension = Path(output_name).suffix.lower()
    normalized_extensions = {
        item.lower() if item.startswith(".") else f".{item.lower()}"
        for item in allowed_extensions
    }
    if extension not in normalized_extensions:
        raise ValueError(f"audio output extension must be one of {sorted(normalized_extensions)}")

    root = Path(output_root).resolve()
    candidate = (root / output_name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("audio output path must remain beneath output root")
    return candidate


def resolve_audio_output_directory(output_root: Path | str, output_dir: Path | str) -> Path:
    """Resolve an output directory and require containment beneath its root."""
    root = Path(output_root).resolve()
    directory = Path(output_dir).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("audio output directory must remain beneath output root")
    return directory


def atomic_write_bytes(output_path: Path, content: bytes) -> None:
    """Atomically replace an audio artifact in its destination directory."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()