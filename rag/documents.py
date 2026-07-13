"""Normalized RAG document and hit helpers."""

from __future__ import annotations

from typing import Any


def normalize_document(record: dict[str, Any]) -> dict[str, Any]:
    """Return a retrieval document with stable fields."""
    metadata = dict(record.get("metadata") or {})
    for key in ("species", "source", "title", "url", "verified"):
        if key in record and key not in metadata:
            metadata[key] = record[key]

    doc_id = str(record.get("id") or metadata.get("id") or metadata.get("url") or "")
    text = str(record.get("text") or record.get("document") or "")
    return {
        "id": doc_id,
        "text": text,
        "metadata": metadata,
    }


def normalize_documents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_document(record) for record in records if record.get("text") or record.get("document")]


def make_hit(
    doc_id: str,
    text: str,
    metadata: dict[str, Any] | None = None,
    score: float = 0.0,
    distance: float | None = None,
    method: str = "unknown",
) -> dict[str, Any]:
    return {
        "id": doc_id,
        "text": text,
        "metadata": dict(metadata or {}),
        "score": score,
        "distance": distance,
        "method": method,
    }
