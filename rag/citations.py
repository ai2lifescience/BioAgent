"""Citation and context helpers for retrieved RAG chunks."""

from __future__ import annotations

from typing import Any


def _source_key(hit: dict[str, Any]) -> tuple[str, str, str]:
    metadata = hit.get("metadata", {})
    return (
        str(metadata.get("url") or ""),
        str(metadata.get("title") or ""),
        str(metadata.get("source") or ""),
    )


def collect_citations(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], str] = {}
    for hit in hits:
        key = _source_key(hit)
        if key in seen:
            hit["citation_id"] = seen[key]
            continue
        citation_id = f"S{len(citations) + 1}"
        seen[key] = citation_id
        hit["citation_id"] = citation_id
        metadata = hit.get("metadata", {})
        citations.append(
            {
                "id": citation_id,
                "title": metadata.get("title"),
                "source": metadata.get("source"),
                "url": metadata.get("url"),
                "pmid": metadata.get("pmid"),
                "year": metadata.get("year"),
            }
        )
    return citations


def build_context(hits: list[dict[str, Any]]) -> str:
    parts = []
    for hit in hits:
        citation_id = hit.get("citation_id", "S?")
        metadata = hit.get("metadata", {})
        title = metadata.get("title") or "Untitled source"
        source = metadata.get("source") or "unknown"
        url = metadata.get("url") or ""
        parts.append(
            f"[{citation_id}] {title} | {source} | {url}\n{hit.get('text', '')}"
        )
    return "\n\n".join(parts)
