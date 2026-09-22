"""Retrieve cited evidence from a durable knowledge collection."""
from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.knowledge import KnowledgeJobStore
from tools.infrastructure.tool_support.artifacts import output, write_json
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.embeddings import embed_texts
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult
from tools.infrastructure.tool_support.evidence_models import EvidenceRecord


class KnowledgeRetrieveResult(FunctionContract):
    collection_id: str
    question: str
    sources: list[EvidenceRecord]
    returned: int
    total: int
    evidence_path: str


def _operation(*, collection_id: str, question: str, top_k: int, context):
    session_id = str((context.user_context or {}).get("session_id") or "").strip()
    if not session_id:
        raise ValueError("Knowledge retrieval requires an active session.")
    store = KnowledgeJobStore()
    collection = store.collection(collection_id, session_id=session_id)
    if collection["chunks"] < 1:
        raise ValueError("Knowledge collection has no indexed content. Wait for ingestion to finish.")
    vector = embed_texts([question], model=collection["embedding_model"])[0]
    hits = store.retrieve(collection_id=collection_id, session_id=session_id, question=question, query_vector=vector, top_k=top_k)
    sources = [hit.record for hit in hits]
    if not sources:
        raise ValueError("No relevant knowledge was found for the question.")
    file = write_json(context, "knowledge_evidence.json", {"schema_version": 1, "sources": [item.model_dump(mode="json") for item in sources]})
    return output(
        {"collection_id": collection_id, "question": question, "sources": [item.model_dump(mode="json") for item in sources],
         "returned": len(sources), "total": collection["chunks"], "evidence_path": file["path"]}, file,
    )


@bio_function_tool(timeout=120)
async def knowledge_retrieve(
    ctx: RunContextWrapper[AgentRunContext],
    collection_id: Annotated[str, Field(min_length=4, max_length=80)],
    question: Annotated[str, Field(min_length=1, max_length=2000)],
    top_k: Annotated[int, Field(ge=1, le=20)] = 8,
) -> FunctionResult[KnowledgeRetrieveResult]:
    """Select bounded, citation-ready excerpts from a session-owned knowledge collection."""
    return await invoke(ctx.context, "knowledge_retrieve", _operation, {"collection_id": collection_id, "question": question, "top_k": top_k}, FunctionResult[KnowledgeRetrieveResult])


__all__ = ["KnowledgeRetrieveResult", "knowledge_retrieve"]
