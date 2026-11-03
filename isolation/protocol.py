"""Bounded control messages and workspace-relative paths; file bytes stay on disk."""
from pathlib import Path, PurePosixPath

MAX_WIRE = 8 * 1024 * 1024


def relative_path(name: str) -> Path:
    if not isinstance(name, str) or not name or len(name) > 512 or "\\" in name or "\x00" in name:
        raise ValueError("Invalid worker file path.")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(name).is_absolute():
        raise ValueError("Worker file path must stay inside its workspace.")
    return Path(*parts)
