"""RAG retrieval pipeline: retrieve, rank, cite, and format evidence."""

from __future__ import annotations

from typing import Any

from rag.citations import build_context, collect_citations
from rag.retriever import retrieve_documents, retrieve_from_collection
from rag.vector_db import DEFAULT_CHROMA_PATH


def _attach_citations(result: dict[str, Any]) -> dict[str, Any]:
    chunks = result.get("chunks", [])
    citations = collect_citations(chunks)
    return {
        **result,
        "citations": citations,
        "context": build_context(chunks),
    }


def retrieve_evidence(
    question: str,
    collection_name: str = "species_kb",
    chroma_path: str = DEFAULT_CHROMA_PATH,
    top_k: int = 5,
    metadata_filters: dict[str, Any] | None = None,
    include_keyword: bool = True,
) -> dict[str, Any]:
    return _attach_citations(
        retrieve_documents(
            question=question,
            collection_name=collection_name,
            chroma_path=chroma_path,
            top_k=top_k,
            metadata_filters=metadata_filters,
            include_keyword=include_keyword,
        )
    )


def retrieve_evidence_from_collection(
    question: str,
    collection,
    top_k: int = 5,
    metadata_filters: dict[str, Any] | None = None,
    include_keyword: bool = True,
) -> dict[str, Any]:
    return _attach_citations(
        retrieve_from_collection(
            question=question,
            collection=collection,
            top_k=top_k,
            metadata_filters=metadata_filters,
            include_keyword=include_keyword,
        )
    )
