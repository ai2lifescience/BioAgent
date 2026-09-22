"""Read one durable knowledge ingestion job."""
from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.knowledge import KnowledgeService
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class KnowledgeStatusResult(FunctionContract):
    job_id: str
    collection_id: str
    status: str
    progress: dict
    error: str | None = None
    created_at: str
    updated_at: str


def _operation(*, job_id: str, context):
    session_id = str((context.user_context or {}).get("session_id") or "").strip()
    if not session_id:
        raise ValueError("Knowledge status requires an active session.")
    return {"status": "ok", "data": KnowledgeService().get_job(job_id, session_id=session_id), "files": [], "evidence": []}


@bio_function_tool(timeout=30)
async def knowledge_status(
    ctx: RunContextWrapper[AgentRunContext],
    job_id: Annotated[str, Field(min_length=4, max_length=100)],
) -> FunctionResult[KnowledgeStatusResult]:
    """Return progress for a session-owned knowledge ingestion job."""
    return await invoke(ctx.context, "knowledge_status", _operation, {"job_id": job_id}, FunctionResult[KnowledgeStatusResult])


__all__ = ["KnowledgeStatusResult", "knowledge_status"]
