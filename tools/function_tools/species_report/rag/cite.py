"""RAG citation tool implementation."""

from __future__ import annotations

from typing import Any

from rag import build_context, collect_citations


def rag_citations_tool(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    copied_chunks = [dict(chunk) for chunk in chunks]
    citations = collect_citations(copied_chunks)
    return {
        "status": "ok",
        "citation_count": len(citations),
        "citations": citations,
        "context": build_context(copied_chunks),
    }
