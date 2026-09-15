"""RAG retrieval tool implementation."""

from __future__ import annotations

from typing import Any

from rag import DEFAULT_CHROMA_PATH, retrieve_evidence


def rag_retrieve_tool(
    question: str,
    collection_name: str = "species_kb",
    chroma_path: str = DEFAULT_CHROMA_PATH,
    top_k: int = 5,
    metadata_filters: dict[str, Any] | None = None,
    include_keyword: bool = True,
) -> dict[str, Any]:
    result = retrieve_evidence(
        question=question,
        collection_name=collection_name,
        chroma_path=chroma_path,
        top_k=top_k,
        metadata_filters=metadata_filters,
        include_keyword=include_keyword,
    )
    return {
        "status": "ok",
        **result,
    }
