"""Runtime model configuration for Pipeline2Agent."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "nemotron-3-super": {
        "label": "Nemotron",
        "deployment": "OpenRouter",
        "cost_tier": "Free",
        "model": os.getenv(
            "AGENT_NEMOTRON_MODEL",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ),
    },
    "gpt-oss": {
        "label": "GPT-OSS",
        "deployment": "OpenRouter",
        "cost_tier": "Low-cost",
        "model": os.getenv("AGENT_GPT_OSS_MODEL", "openai/gpt-oss-120b"),
    },
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "deployment": "OpenRouter",
        "cost_tier": "Standard",
        "model": os.getenv("AGENT_DEEPSEEK_V4_FLASH_MODEL", "deepseek/deepseek-v4-flash"),
    },
    "gpt-5.6-luna": {
        "label": "GPT-5.6 Luna",
        "deployment": "OpenRouter",
        "cost_tier": "Low-cost",
        "model": os.getenv(
            "AGENT_GPT_56_LUNA_MODEL",
            "openai/gpt-5.6-luna",
        ),
    },
    "gpt-5.6-sol": {
        "label": "GPT-5.6 Sol",
        "deployment": "OpenRouter",
        "cost_tier": "Premium",
        "model": os.getenv(
            "AGENT_GPT_56_SOL_MODEL",
            "openai/gpt-5.6-sol",
        ),
    },
    "gemini-3.8-flash": {
        "label": "Gemini 3.8 Flash",
        "deployment": "OpenRouter",
        "cost_tier": "Standard",
        "model": os.getenv(
            "AGENT_GEMINI_38_FLASH_MODEL",
            "google/gemini-3.8-flash",
        ),
    },
}

DEFAULT_AGENT_MODEL_KEY = os.getenv("AGENT_MODEL_KEY", "gpt-5.6-luna")
DEFAULT_MODEL_KEYS = tuple(DEFAULT_MODELS)
DEFAULT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "5"))
DEFAULT_SYNTHESIS_MODEL_KEY = os.getenv("AGENT_SYNTHESIS_MODEL_KEY", DEFAULT_AGENT_MODEL_KEY)
DEFAULT_OPENROUTER_API_BASE = os.getenv(
    "OPENROUTER_API_BASE",
    "https://openrouter.ai/api/v1",
)
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
)


def resolve_model_id(model_name: str | None) -> str:
    """Resolve a catalog alias or preserve an explicit provider-native model ID."""
    name = DEFAULT_AGENT_MODEL_KEY if model_name is None else model_name
    if not name.strip():
        raise ValueError("A model alias or provider-native model ID is required.")
    if name in DEFAULT_MODELS:
        return str(DEFAULT_MODELS[name]["model"])
    return name
