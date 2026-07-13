"""Vector database access for RAG retrieval."""

from __future__ import annotations

import os
from typing import Any

import chromadb

from models.embedding_client import embed_records, embed_texts
from rag.documents import make_hit


DEFAULT_CHROMA_PATH = os.getenv("BIOAGENT_CHROMA_PATH", "runtime/chroma")
DEFAULT_COLLECTION_NAME = "species_kb"


def get_collection(
    collection_name: str = DEFAULT_COLLECTION_NAME,
    chroma_path: str = DEFAULT_CHROMA_PATH,
):
    client = chromadb.PersistentClient(path=chroma_path)
    return client.get_or_create_collection(name=collection_name)


def _clean_metadata_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return str(value)


def _to_metadata(record: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata = {
        "species": record.get("species", ""),
        "source": record.get("source", ""),
        "title": record.get("title", ""),
        "url": record.get("url", ""),
        "verified": bool(record.get("verified", False)),
        **record.get("metadata", {}),
    }
    return {key: _clean_metadata_value(value) for key, value in metadata.items()}


def _where(metadata_filters: dict[str, Any] | None) -> dict[str, Any] | None:
    filters = {
        key: value
        for key, value in (metadata_filters or {}).items()
        if value is not None and value != ""
    }
    if not filters:
        return None
    if len(filters) == 1:
        key, value = next(iter(filters.items()))
        return {key: value}
    return {"$and": [{key: value} for key, value in filters.items()]}


def store_in_chroma(
    records: list[dict[str, Any]],
    collection_name: str = DEFAULT_COLLECTION_NAME,
    chroma_path: str = DEFAULT_CHROMA_PATH,
):
    collection = get_collection(collection_name=collection_name, chroma_path=chroma_path)
    embed_records(records)
    collection.upsert(
        ids=[record["id"] for record in records],
        documents=[record["text"] for record in records],
        embeddings=[record["embedding"] for record in records],
        metadatas=[_to_metadata(record) for record in records],
    )
    return collection


def query_vector_collection(
    question: str,
    collection,
    top_k: int = 5,
    metadata_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    query_embedding = embed_texts([question])[0]
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": max(1, top_k),
        "include": ["documents", "metadatas", "distances"],
    }
    where = _where(metadata_filters)
    if where:
        kwargs["where"] = where
    results = collection.query(**kwargs)

    ids = (results.get("ids") or [[]])[0]
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    hits = []
    for index, doc_id in enumerate(ids):
        distance = distances[index] if index < len(distances) else None
        score = 1.0 / (1.0 + float(distance)) if distance is not None else 0.0
        hits.append(
            make_hit(
                doc_id=str(doc_id),
                text=str(docs[index] if index < len(docs) else ""),
                metadata=metas[index] if index < len(metas) else {},
                score=score,
                distance=distance,
                method="vector",
            )
        )
    return hits


def get_all_documents(
    collection,
    metadata_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
    where = _where(metadata_filters)
    if where:
        kwargs["where"] = where
    results = collection.get(**kwargs)
    ids = results.get("ids") or []
    docs = results.get("documents") or []
    metas = results.get("metadatas") or []
    return [
        make_hit(
            doc_id=str(doc_id),
            text=str(docs[index] if index < len(docs) else ""),
            metadata=metas[index] if index < len(metas) else {},
            method="keyword",
        )
        for index, doc_id in enumerate(ids)
    ]

