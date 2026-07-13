"""Metadata filtering for retrieved RAG chunks."""

from __future__ import annotations

from typing import Any


def matches_metadata_filters(
    metadata: dict[str, Any],
    metadata_filters: dict[str, Any] | None = None,
) -> bool:
    for key, expected in (metadata_filters or {}).items():
        if expected is None or expected == "":
            continue
        if metadata.get(key) != expected:
            return False
    return True


def filter_hits(
    hits: list[dict[str, Any]],
    metadata_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not metadata_filters:
        return hits
    return [
        hit
        for hit in hits
        if matches_metadata_filters(hit.get("metadata", {}), metadata_filters)
    ]
