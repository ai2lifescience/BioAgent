"""Model configuration and runtime clients."""

from .config import (
    DEFAULT_AGENT_MODEL_KEY,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_SKILL_STEPS,
    DEFAULT_MODEL_KEYS,
    DEFAULT_MODELS,
    DEFAULT_OPENROUTER_API_BASE,
    DEFAULT_SYNTHESIS_MODEL_KEY,
    get_default_model,
    get_default_model_id,
)
__all__ = [
    "DEFAULT_AGENT_MODEL_KEY",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_MAX_SKILL_STEPS",
    "DEFAULT_MODEL_KEYS",
    "DEFAULT_MODELS",
    "DEFAULT_OPENROUTER_API_BASE",
    "DEFAULT_SYNTHESIS_MODEL_KEY",
    "get_default_model",
    "get_default_model_id",
    "ModelChatbot",
    "generate_from_messages",
    "generate_text",
    "run_multi_model_messages",
    "run_multi_model_prompt",
]


def __getattr__(name: str):
    if name == "ModelChatbot":
        from .chatbot import ModelChatbot
        return ModelChatbot
    if name in {"generate_from_messages", "generate_text"}:
        from .text_generation import generate_from_messages, generate_text
        return {"generate_from_messages": generate_from_messages, "generate_text": generate_text}[name]
    if name in {"run_multi_model_messages", "run_multi_model_prompt"}:
        from .multi_model import run_multi_model_messages, run_multi_model_prompt
        return {"run_multi_model_messages": run_multi_model_messages, "run_multi_model_prompt": run_multi_model_prompt}[name]
    raise AttributeError(name)
