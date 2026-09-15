"""RAG chunk tool implementation."""

from __future__ import annotations

from typing import Any

from rag import chunk_records


def rag_chunk_tool(
    records: list[dict[str, Any]],
    chunk_chars: int = 1200,
    overlap: int = 180,
) -> dict[str, Any]:
    chunks = chunk_records(records=records, chunk_chars=chunk_chars, overlap=overlap)
    return {
        "status": "ok",
        "record_count": len(records),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
