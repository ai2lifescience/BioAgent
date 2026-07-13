"""RAG vector-store tool implementation."""

from __future__ import annotations

from typing import Any

from rag import DEFAULT_CHROMA_PATH, store_in_chroma


def rag_store_tool(
    records: list[dict[str, Any]],
    collection_name: str = "species_kb",
    chroma_path: str = DEFAULT_CHROMA_PATH,
) -> dict[str, Any]:
    store_in_chroma(
        records,
        collection_name=collection_name,
        chroma_path=chroma_path,
    )
    return {
        "status": "ok",
        "collection_name": collection_name,
        "chroma_path": chroma_path,
        "record_count": len(records),
    }
