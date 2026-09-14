"""OpenRouter access through the official OpenAI Python client."""

from __future__ import annotations

import os
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


def _transport_options() -> dict[str, Any]:
    """Choose a proxy without accidentally inheriting a broken shell proxy.

    ``BIOAGENT_PROXY`` is the explicit override. Otherwise an ``ALL_PROXY``
    value is honored, which supports the common SOCKS-only launch command.
    Set ``BIOAGENT_DISABLE_PROXY=1`` to force a direct connection.
    """
    if os.getenv("BIOAGENT_DISABLE_PROXY", "").strip().lower() in {"1", "true", "yes"}:
        return {"trust_env": False}
    proxy = os.getenv("BIOAGENT_PROXY", "").strip()
    if not proxy:
        proxy = os.getenv("ALL_PROXY", os.getenv("all_proxy", "")).strip()
    if proxy:
        return {"trust_env": False, "proxy": proxy}
    return {"trust_env": False}


def create_client() -> OpenAI:
    options = client_options()
    options["http_client"] = httpx2.Client(timeout=options.pop("timeout"), **_transport_options())
    return OpenAI(**options)


def create_async_client() -> AsyncOpenAI:
    """Create a client owned and closed by one Agents SDK run."""
    options = client_options()
    options["http_client"] = httpx2.AsyncClient(timeout=options.pop("timeout"), **_transport_options())
    return AsyncOpenAI(**options)


def normalize_model_id(model: str) -> str:
    """Accept an old configuration value while sending a native model ID."""
    return model.removeprefix("openrouter/")
