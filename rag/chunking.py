"""Reusable text chunking helpers for RAG ingestion."""

from __future__ import annotations

import hashlib
import re
from typing import Any


DEFAULT_CHUNK_CHARS = 1200
DEFAULT_CHUNK_OVERLAP = 180


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def chunk_text(
    text: str,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    clean = normalize_text(text)
    if not clean:
        return []
    if len(clean) <= chunk_chars:
        return [clean]

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_chars)
        if end < len(clean):
            sentence_boundary = max(
                clean.rfind(". ", start, end),
                clean.rfind("; ", start, end),
                clean.rfind("\n", start, end),
            )
            if sentence_boundary > start + chunk_chars // 2:
                end = sentence_boundary + 1
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def chunk_records(
    records: list[dict[str, Any]],
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for record in records:
        for index, text in enumerate(chunk_text(record["text"], chunk_chars, overlap)):
            digest = hashlib.sha1(
                f"{record['url']}|{index}|{text[:120]}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(
                {
                    "id": f"knowledge_{digest}",
                    "species": record["species"],
                    "source": record["source"],
                    "title": record["title"],
                    "url": record["url"],
                    "verified": bool(record.get("verified", False)),
                    "text": text,
                    "metadata": {
                        **record.get("metadata", {}),
                        "chunk_index": index,
                    },
                }
            )
    return chunks
