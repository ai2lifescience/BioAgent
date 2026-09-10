"""Runtime model configuration for BioAgent."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_LLM_TIMEOUT_SECONDS = max(1, int(os.getenv("BIOAGENT_LLM_TIMEOUT_SECONDS", "60")))


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment override without accepting ambiguous values."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "nemotron-3-super": {
        "label": "Nemotron",
        "model": os.getenv(
            "BIOAGENT_NEMOTRON_MODEL",
            "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        ),
        "answer_instruction": "Be concise and structured.",
        "supports_tool_calling": True,
    },
    "gpt-oss": {
        "label": "GPT-OSS",
        "model": os.getenv("BIOAGENT_GPT_OSS_MODEL", "openrouter/openai/gpt-oss-120b:free"),
        "answer_instruction": "Return concise bullet points.",
        "supports_tool_calling": True,
    },
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "model": os.getenv("BIOAGENT_DEEPSEEK_V4_FLASH_MODEL", "openai/DeepSeek-V4-Flash"),
        "api_base": os.getenv(
            "BIOAGENT_DEEPSEEK_V4_FLASH_API_BASE",
            "http://192.168.116.46:8088/v1",
        ),
        "api_key": os.getenv("BIOAGENT_DEEPSEEK_V4_FLASH_API_KEY", "noapi"),
        "answer_instruction": "Be concise and structured.",
        "timeout_seconds": max(
            1,
            int(
                os.getenv(
                    "BIOAGENT_DEEPSEEK_V4_FLASH_TIMEOUT_SECONDS",
                    str(DEFAULT_LLM_TIMEOUT_SECONDS),
                )
            ),
        ),
        "supports_tool_calling": _env_bool(
            "BIOAGENT_DEEPSEEK_V4_FLASH_SUPPORTS_TOOL_CALLING",
            False,
        ),
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
