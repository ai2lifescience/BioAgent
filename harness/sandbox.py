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

from tools.infrastructure.workspace import workspace_file_metadata
from tools.infrastructure.workspace.sdk import list_files
from .tracing import configure_tracing

if TYPE_CHECKING:
    from .sessions import SessionMetadata

WORKSPACES_DIR = Path(os.getenv("AGENT_SESSIONS_DIR", "runtime/sessions")).resolve()
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
    # A website binding is session-scoped and must survive durable worker
    # handoff and SDK approval resume without exposing its secret to prompts.
    if isinstance(session.metadata.get("website_binding"), dict):
        run["website_binding"] = dict(session.metadata["website_binding"])
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


async def upload_file(session: BaseSandboxSession, filename: str, data: bytes) -> dict:
    if not data:
        raise ValueError("Uploaded file is empty.")
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name).strip("._") or "upload.bin"
    path = Path("uploads") / f"{uuid4().hex[:12]}_{name}"
    await session.mkdir("uploads", parents=True)
    await session.write(path, BytesIO(data))
    return {
        "path": path.as_posix(),
        "workspace_path": path.as_posix(),
        "name": name,
        "size": len(data),
        **workspace_file_metadata(path, uploaded=True),
    }


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
    """Filesystem capabilities accompany the guarded local pipeline ShellTool."""
    return [Filesystem()]
