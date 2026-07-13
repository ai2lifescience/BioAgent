"""Model configuration and runtime clients."""

from .config import (
    DEFAULT_AGENT_MODEL_KEY,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_SKILL_STEPS,
    DEFAULT_MODEL_KEYS,
    DEFAULT_MODELS,
    DEFAULT_OPENROUTER_API_BASE,
    DEFAULT_SYNTHESIS_MODEL_KEY,
    configure_runtime_env,
    get_default_model,
    get_default_model_id,
)
from .chatbot import ModelChatbot
from .llm_client import LLMClient
from .multi_model import run_multi_model_messages, run_multi_model_prompt
from .text_generation import generate_from_messages, generate_text

__all__ = [
    "DEFAULT_AGENT_MODEL_KEY",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_MAX_SKILL_STEPS",
    "DEFAULT_MODEL_KEYS",
    "DEFAULT_MODELS",
    "DEFAULT_OPENROUTER_API_BASE",
    "DEFAULT_SYNTHESIS_MODEL_KEY",
    "LLMClient",
    "ModelChatbot",
    "configure_runtime_env",
    "generate_from_messages",
    "generate_text",
    "get_default_model",
    "get_default_model_id",
    "run_multi_model_messages",
    "run_multi_model_prompt",
]
