"""Embedding helpers for species KB records and queries."""

from __future__ import annotations

from typing import Any, Iterable

from .config import DEFAULT_EMBEDDING_MODEL
from .openrouter_client import create_client, normalize_model_id


def embed_texts(
    texts: Iterable[str],
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> list[list[float]]:
    payload = list(texts)
    if not payload:
        return []
    with create_client() as client:
        response = client.embeddings.create(
            model=normalize_model_id(model), input=payload, encoding_format="float"
        )
    items = sorted(response.data, key=lambda item: item.index)
    if len(items) != len(payload):
        raise RuntimeError("The embedding provider returned an incomplete batch.")
    return [item.embedding for item in items]


def embed_records(
    records: list[dict[str, Any]],
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> list[dict[str, Any]]:
    vectors = embed_texts([record["text"] for record in records], model=model)
    for record, vector in zip(records, vectors):
        record["embedding"] = vector
    return records
