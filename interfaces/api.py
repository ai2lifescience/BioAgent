"""Programmatic API interface for Pipeline2Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from agents import SQLiteSession

from harness import runtime
from harness.runtime import delete_session, list_sessions, resume_agent, run_agent, update_session  # noqa: F401
from harness.sandbox import delete_file, list_files, open_workspace, read_file, upload_file
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_TURNS
from harness.jobs import get_queue, result_status
from tools.infrastructure.knowledge import KnowledgeService


def enqueue_request(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_turns: int = DEFAULT_MAX_TURNS,
    website: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Queue a durable model run and return its stable run identifier."""
    identifier = str(session_id or "").strip() or str(uuid4())
    # Create/validate the session before starting a worker. This makes a run
    # submitted without a browser-generated session ID addressable immediately
    # and prevents invalid IDs from leaving orphaned queue rows.
    turns = max(1, min(int(max_turns), 20))
    with runtime.STATE_STORE.locked_session(identifier, request) as (session, _):
        if session.metadata.get("pending_run"):
            raise ValueError("Resolve the pending tool approval before sending another request.")
        if website is not None:
            from harness.website import get_bridge
            binding = get_bridge().binding_for_run(
                str(website.get("binding_id", "")), str(website.get("token", "")), identifier
            )
            session.metadata["website_binding"] = binding
        job = get_queue().enqueue(request, identifier, model_key, turns)
        session.metadata["last_run_id"] = job["run_id"]
        return job


def enqueue_approval(session_id: str, approved: bool, approval_id: str) -> dict[str, Any] | None:
    """Resume a web job in a detached worker, retaining its existing run ID."""
    return get_queue().resume(session_id, approved, approval_id)


def get_run(run_id: str) -> dict[str, Any]:
    return get_queue().get(str(run_id or "").strip())


def get_run_events(run_id: str, after: int = -1) -> list[dict[str, Any]]:
    return get_queue().events(str(run_id or "").strip(), int(after))


def get_knowledge_job(job_id: str, session_id: str) -> dict[str, Any]:
    """Return one session-owned durable knowledge job."""
    return KnowledgeService().get_job(str(job_id or "").strip(), session_id=str(session_id or "").strip())


def get_knowledge_job_events(job_id: str, session_id: str, after: int = -1) -> list[dict[str, Any]]:
    """Return resumable knowledge ingestion events for one session."""
    return KnowledgeService().events(
        str(job_id or "").strip(), session_id=str(session_id or "").strip(), after=int(after)
    )


def list_runs(session_id: str | None = None) -> list[dict[str, Any]]:
    return get_queue().list(str(session_id or "").strip() or None)


def handle_request(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_turns: int = DEFAULT_MAX_TURNS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run Pipeline2Agent from application code."""
    return run_agent(request, session_id, model_key, max_turns, log_fn)


def handle_approval(
    session_id: str,
    approved: bool,
    approval_id: str,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Approve or reject the pending SDK tool call for a session."""
    result = resume_agent(session_id, approved, approval_id, log_fn=log_fn)
    queue = get_queue()
    pending = queue.pending_for_session(session_id)
    if pending is not None:
        queue_status = result_status(result)
        queue.update(
            pending["run_id"],
            queue_status,
            result=result,
            error=result.get("answer") if queue_status == "failed" else None,
        )
    return result


def update_session_metadata(
    session_id: str,
    *,
    title: str | None = None,
    pinned: bool | None = None,
) -> dict[str, Any]:
    """Rename or pin a conversation in the application session index."""
    return update_session(session_id, title=title, pinned=pinned)


def list_session_messages(session_id: str) -> dict[str, Any]:
    """Read displayable conversation items from the SDK session store."""
    import asyncio

    identifier = str(session_id or "").strip()
    if not identifier:
        return {"session_id": None, "messages": []}
    metadata = runtime.STATE_STORE.get_session(identifier)

    async def _list() -> dict[str, Any]:
        items = []
        if Path(runtime.SESSION_DB).exists():
            session = SQLiteSession(identifier, db_path=runtime.SESSION_DB)
            try:
                items = await session.get_items()
            finally:
                session.close()
        messages = []
        for item in items:
            role = str(item.get("role") or "") if isinstance(item, dict) else ""
            if role not in {"user", "assistant"}:
                continue
            text = _session_item_text(item.get("content"))
            if text:
                messages.append({"role": role, "text": text})
        stored_results = metadata.metadata.get("message_results", []) if metadata else []
        if not isinstance(stored_results, list):
            stored_results = []
        result_index = 0
        current_request = ""
        for message in messages:
            if message.get("role") == "user":
                current_request = str(message.get("text") or "")
                continue
            if message.get("role") != "assistant":
                continue
            while result_index < len(stored_results):
                entry = stored_results[result_index]
                result_index += 1
                if not isinstance(entry, dict):
                    continue
                # Current metadata stores the request/answer pair so results
                # still align when a session predates structured-result
                # persistence. Accept the older direct-result shape too.
                if "result" in entry:
                    if (
                        str(entry.get("request") or "") == current_request
                        and str(entry.get("answer") or "") == str(message.get("text") or "")
                    ):
                        if isinstance(entry.get("result"), dict):
                            message["result"] = entry["result"]
                        break
                    continue
                message["result"] = entry
                break
        last_approval = metadata.metadata.get("last_approval") if metadata else None
        if isinstance(last_approval, dict):
            for message in reversed(messages):
                if message.get("role") == "assistant":
                    message.setdefault("result", {})["approval_decision"] = last_approval
                    break
        pending = metadata.metadata.get("pending_run") if metadata else None
        return {
            "session_id": identifier,
            "messages": messages,
            "pending_approval": {
                "session_id": identifier,
                "answer": "Review the requested tool arguments and approve or reject each pending call.",
                "status": "pending_approval",
                "approval_required": True,
                "approvals": pending["approvals"],
            } if pending else None,
        }

    return asyncio.run(_list())


def _session_item_text(content: Any) -> str:
    """Extract readable text while ignoring tool-call metadata."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [_session_item_text(item) for item in content]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        for key in ("text", "output_text", "content"):
            if key in content:
                value = _session_item_text(content[key])
                if value:
                    return value
    return ""


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

    with runtime.STATE_STORE.locked_session(identifier):
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
