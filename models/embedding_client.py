"""Embedding helpers for species KB records and queries."""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

from .config import DEFAULT_EMBEDDING_MODEL, DEFAULT_OPENROUTER_API_BASE, configure_runtime_env


def _load_embedding_function():
    configure_runtime_env()
    try:
        import litellm
        from litellm import embedding
    except ModuleNotFoundError as exc:
        missing = exc.name or "required package"
        raise RuntimeError(
            f"Missing dependency '{missing}'. Install project dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    litellm.suppress_debug_info = True
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)
    logging.getLogger("litellm").setLevel(logging.ERROR)
    return embedding


def _provider_kwargs() -> dict[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")
    return {
        "api_key": api_key,
        "api_base": os.getenv("OPENROUTER_API_BASE", DEFAULT_OPENROUTER_API_BASE),
    }


def _resolve_model(model: str) -> str:
    if model.startswith("openrouter/"):
        return model
    return f"openrouter/{model}"


def embed_texts(
    texts: Iterable[str],
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> list[list[float]]:
    payload = list(texts)
    if not payload:
        return []
    embedding = _load_embedding_function()
    resolved_model = _resolve_model(model)
    response = embedding(model=resolved_model, input=payload, **_provider_kwargs())
    return [item["embedding"] for item in response.data]


def embed_records(
    records: list[dict[str, Any]],
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> list[dict[str, Any]]:
    vectors = embed_texts([record["text"] for record in records], model=model)
    for record, vector in zip(records, vectors):
        record["embedding"] = vector
    return records
