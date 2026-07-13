"""Keyword retrieval for exact biological terms."""

from __future__ import annotations

import math
import re
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def keyword_score(query: str, text: str) -> float:
    query_terms = set(tokenize(query))
    if not query_terms:
        return 0.0
    text_terms = tokenize(text)
    if not text_terms:
        return 0.0
    counts = {term: text_terms.count(term) for term in query_terms}
    matched = sum(1 for count in counts.values() if count)
    frequency = sum(math.log1p(count) for count in counts.values())
    return matched / len(query_terms) + frequency / max(1, len(text_terms))


def keyword_search(
    query: str,
    documents: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    hits = []
    for document in documents:
        text = document.get("text", "")
        metadata_text = " ".join(str(value) for value in document.get("metadata", {}).values())
        score = keyword_score(query, f"{text} {metadata_text}")
        if score <= 0:
            continue
        hit = dict(document)
        hit["score"] = score
        hit["method"] = "keyword"
        hits.append(hit)
    return sorted(hits, key=lambda item: item.get("score", 0.0), reverse=True)[:top_k]
