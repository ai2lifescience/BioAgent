"""Programmatic API interface for BioAgent."""

from __future__ import annotations

from typing import Any, Callable

from harness.runtime import delete_session, list_sessions, resume_bioagent, run_bioagent
from harness.sandbox import delete_file, list_files, open_workspace, read_file, upload_file
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS


def handle_request(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run BioAgent from application code."""
    return run_bioagent(request, session_id, model_key, max_skill_steps, log_fn)


def handle_approval(
    session_id: str,
    approved: bool,
    approval_id: str,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Approve or reject the pending SDK tool call for a session."""
    return resume_bioagent(session_id, approved, approval_id, log_fn=log_fn)


def write_workspace_file(
    session_id: str | None,
    filename: str,
    data: bytes,
    content_type: str = "",
) -> dict[str, Any]:
    """Store one uploaded file in the SDK sandbox workspace."""
    import asyncio
    from uuid import uuid4
    identifier = str(session_id or "").strip() or str(uuid4())

    async def _store() -> dict[str, Any]:
        async with open_workspace(identifier) as workspace:
            result = await upload_file(workspace, filename, data)
            result["session_id"] = identifier
            return result

    return asyncio.run(_store())


def list_workspace_files(session_id: str | None) -> dict[str, Any]:
    """List files in one SDK sandbox workspace."""
    import asyncio
    identifier = str(session_id or "").strip()
    if not identifier:
        return {"session_id": None, "files": []}

    async def _list() -> dict[str, Any]:
        async with open_workspace(identifier) as workspace:
            return {"session_id": identifier, "files": await list_files(workspace)}

    return asyncio.run(_list())


def delete_workspace_file(session_id: str, path: str) -> bool:
    """Delete one workspace file using its workspace-relative path."""
    import asyncio

    async def _delete() -> bool:
        try:
            async with open_workspace(session_id) as workspace:
                await delete_file(workspace, path)
            return True
        except (FileNotFoundError, ValueError):
            return False

    return asyncio.run(_delete())


def read_workspace_file(session_id: str, path: str) -> bytes:
    """Read one workspace file through the SDK sandbox filesystem."""
    import asyncio

    async def _read() -> bytes:
        async with open_workspace(session_id) as workspace:
            return await read_file(workspace, path)

    return asyncio.run(_read())
