"""Workspace operations that use the Agents SDK sandbox session."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.sandbox.files import EntryKind
from agents.sandbox.session.base_sandbox_session import BaseSandboxSession

from .artifacts import workspace_file_metadata


async def list_files(session: BaseSandboxSession) -> list[dict[str, Any]]:
    """List regular workspace files without exposing host paths."""
    root = Path(session.state.manifest.root)
    directories = [root]
    files: list[dict[str, Any]] = []
    while directories:
        for entry in await session.ls(directories.pop()):
            path = Path(entry.path)
            if path.name.startswith("."):
                continue
            if entry.kind == EntryKind.DIRECTORY:
                directories.append(path)
            elif entry.kind == EntryKind.FILE:
                relative = path.relative_to(root).as_posix()
                files.append({
                    "path": relative,
                    "workspace_path": relative,
                    "name": path.name,
                    "size": entry.size,
                    "modified_at": path.stat().st_mtime_ns,
                    **workspace_file_metadata(path, uploaded=relative.startswith("uploads/")),
                })
    return sorted(files, key=lambda item: (item["modified_at"], item["path"]))


__all__ = ["list_files"]
