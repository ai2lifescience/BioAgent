"""Chunking, embedding persistence, and hybrid retrieval for knowledge pages."""
from __future__ import annotations

import json
import math
import re

from tools.infrastructure.tool_support.evidence_models import EvidenceRecord

from .models import KnowledgePage, KnowledgeSearchHit
from .repository import KnowledgeRepository


DEFAULT_CHUNK_CHARS = 1200
DEFAULT_CHUNK_OVERLAP = 180


def chunk_page(page: KnowledgePage, *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split one normalized page into bounded overlapping excerpts."""
    if chunk_chars < 1 or not 0 <= overlap < chunk_chars:
        raise ValueError("Chunk overlap must be nonnegative and smaller than chunk size.")
    values: list[str] = []
    for offset in range(0, len(page.text), max(1, chunk_chars - overlap)):
        excerpt = page.text[offset:offset + chunk_chars]
        if excerpt.strip():
            values.append(excerpt)
        if offset + chunk_chars >= len(page.text):
            break
    return values


class KnowledgeIndexer:
    """Own the document-to-chunk and chunk-to-evidence transformations."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def changed_pages(self, *, collection_id: str, session_id: str, pages: list[KnowledgePage]) -> list[KnowledgePage]:
        return self.repository.changed_pages(collection_id=collection_id, session_id=session_id, pages=pages)

    def chunk_texts(self, pages: list[KnowledgePage], *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
        return [excerpt for page in pages for excerpt in chunk_page(page, chunk_chars=chunk_chars, overlap=overlap)]

    def index(
        self,
        *,
        collection_id: str,
        session_id: str,
        pages: list[KnowledgePage],
        vectors: list[list[float]],
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> dict[str, int]:
        page_chunks: list[list[tuple[str, list[float]]]] = []
        position = 0
        for page in pages:
            excerpts = chunk_page(page, chunk_chars=chunk_chars, overlap=overlap)
            chunks: list[tuple[str, list[float]]] = []
            for excerpt in excerpts:
                if position >= len(vectors):
                    raise ValueError("Embedding count did not match knowledge chunks.")
                chunks.append((excerpt, vectors[position]))
                position += 1
            page_chunks.append(chunks)
        if position != len(vectors):
            raise ValueError("Embedding count exceeded knowledge chunks.")
        return self.repository.replace_pages(
            collection_id=collection_id,
            session_id=session_id,
            pages=pages,
            page_chunks=page_chunks,
        )

    def retrieve(
        self,
        *,
        collection_id: str,
        session_id: str,
        question: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[KnowledgeSearchHit]:
        terms = set(re.findall(r"\w+", question.lower()))

        def cosine(vector: list[float]) -> float:
            if len(vector) != len(query_vector) or not query_vector:
                return 0.0
            denominator = math.sqrt(
                sum(value * value for value in vector) * sum(value * value for value in query_vector)
            )
            return sum(a * b for a, b in zip(vector, query_vector)) / denominator if denominator else 0.0

        scored: list[KnowledgeSearchHit] = []
        for row in self.repository.chunk_rows(collection_id=collection_id, session_id=session_id):
            lexical_tokens = set(re.findall(r"\w+", (row["title"] + " " + row["excerpt"]).lower()))
            lexical = len(terms & lexical_tokens) / max(1, len(terms))
            score = 0.75 * cosine(json.loads(row["vector"])) + 0.25 * lexical
            record = EvidenceRecord(
                id=row["chunk_id"],
                title=row["title"],
                url=row["canonical_url"],
                source="knowledge",
                text=row["excerpt"],
                retrieved_at=row["fetched_at"],
            )
            scored.append(KnowledgeSearchHit(score=score, record=record))
        scored.sort(key=lambda item: (-item.score, item.record.id))
        return scored[:top_k]


__all__ = ["DEFAULT_CHUNK_CHARS", "DEFAULT_CHUNK_OVERLAP", "KnowledgeIndexer", "chunk_page"]
