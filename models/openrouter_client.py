"""OpenRouter access through the official OpenAI Python client."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx2
from openai import AsyncOpenAI, OpenAI

from .config import DEFAULT_OPENROUTER_API_BASE


def client_options() -> dict[str, Any]:
    """Load credentials only when a request client is constructed."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for model requests.")
    headers = {"X-OpenRouter-Title": "BioAgent"}
    if os.getenv("BIOAGENT_SITE_URL"):
        headers["HTTP-Referer"] = os.environ["BIOAGENT_SITE_URL"]
    return {
        "api_key": api_key,
        "base_url": os.getenv("OPENROUTER_API_BASE", DEFAULT_OPENROUTER_API_BASE),
        "default_headers": headers,
        "timeout": float(os.getenv("BIOAGENT_MODEL_TIMEOUT_SECONDS", "120")),
        "max_retries": int(os.getenv("BIOAGENT_MODEL_MAX_RETRIES", "2")),
    }


def create_client() -> OpenAI:
    options = client_options()
    options["http_client"] = httpx2.Client(
        timeout=options.pop("timeout"),
        trust_env=False,
    )
    return OpenAI(**options)


@lru_cache(maxsize=1)
def create_async_client() -> AsyncOpenAI:
    """Return the process-wide async client used by Agents SDK model calls."""
    options = client_options()
    options["http_client"] = httpx2.AsyncClient(
        timeout=options.pop("timeout"),
        trust_env=False,
    )
    return AsyncOpenAI(**options)


def normalize_model_id(model: str) -> str:
    """Accept an old configuration value while sending a native model ID."""
    return model.removeprefix("openrouter/")
