"""Submit a durable web knowledge ingestion job."""
from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.knowledge import KnowledgeService
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class KnowledgeJobResult(FunctionContract):
    job_id: str
    collection_id: str
    status: str
    progress: dict
    error: str | None = None
    created_at: str
    updated_at: str


def _operation(*, request: str, collection_id: str | None, seed_urls: list[str], allowed_domains: list[str], max_pages: int, max_depth: int, refresh: bool, context):
    session_id = str((context.user_context or {}).get("session_id") or "").strip()
    if not session_id:
        raise ValueError("Knowledge ingestion requires an active session.")
    job = KnowledgeService().enqueue(
        session_id=session_id, request=request.strip(), collection_id=collection_id,
        seed_urls=seed_urls, allowed_domains=allowed_domains, max_pages=max_pages,
        max_depth=max_depth, refresh=refresh,
    )
    return {"status": "ok", "data": job, "files": [], "evidence": []}


@bio_function_tool(timeout=60)
async def knowledge_ingest(
    ctx: RunContextWrapper[AgentRunContext],
    request: Annotated[str, Field(min_length=3, max_length=2000, description="Knowledge request that determines what should be discovered and indexed.")],
    collection_id: Annotated[str | None, Field(max_length=80, description="Existing session-owned collection to refresh; omit to create one.")] = None,
    seed_urls: Annotated[list[str] | None, Field(max_length=10, description="Optional public URLs from which to start crawling.")] = None,
    allowed_domains: Annotated[list[str] | None, Field(max_length=10, description="Optional host allowlist for discovery and crawling.")] = None,
    max_pages: Annotated[int, Field(ge=1, le=100)] = 20,
    max_depth: Annotated[int, Field(ge=0, le=3)] = 1,
    refresh: bool = False,
) -> FunctionResult[KnowledgeJobResult]:
    """Queue bounded public-web ingestion into a durable session-owned knowledge collection."""
    return await invoke(
        ctx.context, "knowledge_ingest", _operation,
        {"request": request, "collection_id": collection_id, "seed_urls": seed_urls or [],
         "allowed_domains": allowed_domains or [], "max_pages": max_pages, "max_depth": max_depth, "refresh": refresh},
        FunctionResult[KnowledgeJobResult],
    )


__all__ = ["KnowledgeJobResult", "knowledge_ingest"]
