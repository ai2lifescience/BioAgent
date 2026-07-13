"""Hybrid RAG document retriever."""

from __future__ import annotations

from typing import Any

from rag.filters import filter_hits
from rag.keyword_search import keyword_search
from rag.ranker import rank_hits
from rag.vector_db import (
    DEFAULT_CHROMA_PATH,
    get_all_documents,
    get_collection,
    query_vector_collection,
)


def retrieve_from_collection(
    question: str,
    collection,
    top_k: int = 5,
    metadata_filters: dict[str, Any] | None = None,
    include_keyword: bool = True,
) -> dict[str, Any]:
    candidate_limit = max(top_k * 3, top_k)
    hits = query_vector_collection(
        question=question,
        collection=collection,
        top_k=candidate_limit,
        metadata_filters=metadata_filters,
    )
    methods = ["vector"]

    if include_keyword:
        documents = get_all_documents(collection=collection, metadata_filters=metadata_filters)
        hits.extend(keyword_search(query=question, documents=documents, top_k=candidate_limit))
        methods.append("keyword")

    filtered = filter_hits(hits, metadata_filters=metadata_filters)
    ranked = rank_hits(filtered, top_k=top_k)
    return {
        "question": question,
        "chunks": ranked,
        "chunk_count": len(ranked),
        "top_k": top_k,
        "methods": methods,
        "metadata_filters": metadata_filters or {},
    }


def retrieve_documents(
    question: str,
    collection_name: str = "species_kb",
    chroma_path: str = DEFAULT_CHROMA_PATH,
    top_k: int = 5,
    metadata_filters: dict[str, Any] | None = None,
    include_keyword: bool = True,
) -> dict[str, Any]:
    collection = get_collection(collection_name=collection_name, chroma_path=chroma_path)
    result = retrieve_from_collection(
        question=question,
        collection=collection,
        top_k=top_k,
        metadata_filters=metadata_filters,
        include_keyword=include_keyword,
    )
    result.update(
        {
            "collection_name": collection_name,
            "chroma_path": chroma_path,
        }
    )
    return result
