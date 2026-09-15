"""SDK Unix-local workspace lifecycle and file operations.

Files are the source of truth. Uploads, downloads, listing, and deletion use
the SDK sandbox filesystem, with no application artifact registry.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO
import asyncio
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING
from uuid import uuid4

from agents.sandbox import Manifest
from agents.sandbox.capabilities import Filesystem
from agents.sandbox.files import EntryKind
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
from agents.sandbox.session.base_sandbox_session import BaseSandboxSession
from agents.sandbox.snapshot import NoopSnapshotSpec

from tools.common.files import artifact_content_type, artifact_kind
from .tracing import configure_tracing

if TYPE_CHECKING:
    from .sessions import SessionMetadata

WORKSPACES_DIR = Path(os.getenv("BIOAGENT_SESSIONS_DIR", "runtime/sessions")).resolve()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
configure_tracing()


def session_root(session_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("Invalid session_id.")
    root = WORKSPACES_DIR / session_id
    if root.is_symlink():
        raise ValueError("Workspace roots cannot be symbolic links.")
    return root


def prepare_run(session: SessionMetadata) -> dict[str, str]:
    """Set per-run paths inside the session workspace."""
    root = session_root(session.session_id)
    run_id = str(uuid4())
    run = {
        "run_id": run_id,
        "session_dir": str(root),
        "runtime_dir": str(root / "runs" / run_id),
        "workspace_dir": str(root / "outputs"),
    }
    session.metadata["run"] = run
    return run


@asynccontextmanager
async def open_workspace(session_id: str):
    """Open the persistent local workspace and close SDK resources afterward."""
    client = UnixLocalSandboxClient()
    session = await client.create(
        manifest=Manifest(root=str(session_root(session_id))),
        snapshot=NoopSnapshotSpec(),
    )
    try:
        await session.start()
        yield session
    finally:
        await session.aclose()


def relative_file_path(path: str) -> Path:
    """Validate the public contract: a file path relative to the workspace."""
    candidate = Path(path)
    if not path or candidate.is_absolute() or ".." in candidate.parts or candidate == Path("."):
        raise ValueError("path must be a file path relative to the session workspace.")
    if any(part.startswith(".") for part in candidate.parts):
        raise ValueError("Hidden workspace files are private to the runtime.")
    return candidate


async def list_files(session: BaseSandboxSession) -> list[dict]:
    """List regular workspace files using SDK metadata; never follow symlinks."""
    root = Path(session.state.manifest.root)
    directories = [root]
    files = []
    while directories:
        for entry in await session.ls(directories.pop()):
            path = Path(entry.path)
            if path.name.startswith("."):
                continue
            if entry.kind == EntryKind.DIRECTORY:
                directories.append(path)
            elif entry.kind == EntryKind.FILE:
                relative = path.relative_to(root).as_posix()
                project_path = (
                    path.relative_to(PROJECT_ROOT).as_posix()
                    if path.is_relative_to(PROJECT_ROOT)
                    else str(path)
                )
                files.append({
                    "path": project_path,
                    "workspace_path": relative,
                    "name": path.name,
                    "size": entry.size,
                    "modified_at": path.stat().st_mtime_ns,
                    "kind": "upload" if relative.startswith("uploads/") else artifact_kind(str(path), "path") or "file",
                    "content_type": artifact_content_type(path),
                })
    return sorted(files, key=lambda item: (item["modified_at"], item["path"]))


async def upload_file(session: BaseSandboxSession, filename: str, data: bytes) -> dict:
    if not data:
        raise ValueError("Uploaded file is empty.")
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name).strip("._") or "upload.bin"
    path = Path("uploads") / f"{uuid4().hex[:12]}_{name}"
    await session.mkdir("uploads", parents=True)
    await session.write(path, BytesIO(data))
    project_path = (Path(session.state.manifest.root) / path).resolve()
    display_path = (
        project_path.relative_to(PROJECT_ROOT).as_posix()
        if project_path.is_relative_to(PROJECT_ROOT)
        else str(project_path)
    )
    return {"path": display_path,
            "workspace_path": path.as_posix(), "name": name, "size": len(data),
            "kind": "upload", "content_type": artifact_content_type(path)}


async def read_file(session: BaseSandboxSession, path: str) -> bytes:
    with await session.read(relative_file_path(path)) as stream:
        return stream.read()


async def delete_file(session: BaseSandboxSession, path: str) -> None:
    await session.rm(relative_file_path(path))


async def clear_workspace(session_id: str) -> None:
    """Remove all user and run files through the SDK filesystem API."""
    async with open_workspace(session_id) as session:
        root = Path(session.state.manifest.root)
        for entry in await session.ls("."):
            path = Path(entry.path)
            if path.name.startswith("."):
                continue
            relative = path.relative_to(root)
            await session.rm(relative, recursive=entry.kind == EntryKind.DIRECTORY)


def delete_workspace(session_id: str) -> None:
    """Synchronously clear one workspace for API and CLI callers."""
    asyncio.run(clear_workspace(session_id))


def sandbox_capabilities() -> list[Filesystem]:
    """Keep command execution behind approval-controlled FunctionTools."""
    return [Filesystem()]
