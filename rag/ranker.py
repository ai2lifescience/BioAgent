"""Rank and deduplicate retrieved RAG chunks."""

from __future__ import annotations

from typing import Any


METHOD_WEIGHTS = {
    "vector": 1.0,
    "keyword": 0.8,
    "hybrid": 1.2,
}


def deduplicate_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for hit in hits:
        hit_id = str(hit.get("id") or "")
        if not hit_id:
            continue
        existing = by_id.get(hit_id)
        if existing is None:
            by_id[hit_id] = dict(hit)
            continue
        existing_methods = set(str(existing.get("method", "")).split("+"))
        existing_methods.add(str(hit.get("method", "")))
        existing["method"] = "+".join(sorted(method for method in existing_methods if method))
        existing["score"] = max(float(existing.get("score", 0.0)), float(hit.get("score", 0.0)))
        existing["score"] += 0.15
    return list(by_id.values())


def rank_hits(hits: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    ranked = []
    for hit in deduplicate_hits(hits):
        methods = str(hit.get("method", "")).split("+")
        method_boost = max(METHOD_WEIGHTS.get(method, 0.5) for method in methods if method)
        item = dict(hit)
        item["rank_score"] = float(item.get("score", 0.0)) * method_boost
        ranked.append(item)
    ranked.sort(key=lambda item: item.get("rank_score", 0.0), reverse=True)
    return ranked[: max(1, top_k)]
