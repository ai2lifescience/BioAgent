"""Runtime model configuration for BioAgent."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "nemotron-3-super": {
        "label": "Nemotron",
        "deployment": "OpenRouter",
        "cost_tier": "Free",
        "model": os.getenv(
            "BIOAGENT_NEMOTRON_MODEL",
            "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        ),
        "answer_instruction": "Be concise and structured.",
    },
    "gpt-oss": {
        "label": "GPT-OSS",
        "deployment": "OpenRouter",
        "cost_tier": "Low-cost",
        "model": os.getenv("BIOAGENT_GPT_OSS_MODEL", "openrouter/openai/gpt-oss-120b"),
        "answer_instruction": "Return concise bullet points.",
    },
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "deployment": "Local endpoint",
        "cost_tier": "Local",
        "model": os.getenv("BIOAGENT_DEEPSEEK_V4_FLASH_MODEL", "openai/DeepSeek-V4-Flash"),
        "api_base": os.getenv(
            "BIOAGENT_DEEPSEEK_V4_FLASH_API_BASE",
            "http://192.168.116.46:8088/v1",
        ),
        "api_key": os.getenv("BIOAGENT_DEEPSEEK_V4_FLASH_API_KEY", "noapi"),
        "answer_instruction": "Be concise and structured.",
    },
    "gpt-5.6-luna": {
        "label": "GPT-5.6 Luna",
        "deployment": "OpenRouter",
        "cost_tier": "Low-cost",
        "model": os.getenv(
            "BIOAGENT_GPT_56_LUNA_MODEL",
            "openrouter/openai/gpt-5.6-luna",
        ),
        "answer_instruction": "Be concise and structured.",
    },
    "gpt-5.6-sol": {
        "label": "GPT-5.6 Sol",
        "deployment": "OpenRouter",
        "cost_tier": "Premium",
        "model": os.getenv(
            "BIOAGENT_GPT_56_SOL_MODEL",
            "openrouter/openai/gpt-5.6-sol",
        ),
        "answer_instruction": "Use careful multi-step reasoning and return a structured answer.",
    },
    "gemini-3.8-flash": {
        "label": "Gemini 3.8 Flash",
        "deployment": "OpenRouter",
        "cost_tier": "Standard",
        "model": os.getenv(
            "BIOAGENT_GEMINI_38_FLASH_MODEL",
            "openrouter/google/gemini-3.8-flash",
        ),
        "answer_instruction": "Be concise and structured.",
    },
}

DEFAULT_AGENT_MODEL_KEY = os.getenv("BIOAGENT_AGENT_MODEL_KEY", "nemotron-3-super")
DEFAULT_MODEL_KEYS = tuple(DEFAULT_MODELS)
DEFAULT_MAX_SKILL_STEPS = int(os.getenv("BIOAGENT_MAX_SKILL_STEPS", "5"))
DEFAULT_SYNTHESIS_MODEL_KEY = os.getenv("BIOAGENT_SYNTHESIS_MODEL_KEY", DEFAULT_AGENT_MODEL_KEY)
DEFAULT_OPENROUTER_API_BASE = os.getenv(
    "OPENROUTER_API_BASE",
    "https://openrouter.ai/api/v1",
)
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
)


def configure_runtime_env() -> None:
    """Set non-secret runtime defaults used by LiteLLM and embedding calls."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    os.environ.setdefault("OPENROUTER_API_BASE", DEFAULT_OPENROUTER_API_BASE)
    os.environ.setdefault("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def get_default_model(model_key: str) -> dict[str, Any]:
    try:
        return DEFAULT_MODELS[model_key]
    except KeyError as exc:
        available = ", ".join(sorted(DEFAULT_MODELS))
        raise KeyError(f"Unknown model key '{model_key}'. Available models: {available}") from exc


def get_default_model_id(model_key: str) -> str:
    return str(get_default_model(model_key)["model"])
