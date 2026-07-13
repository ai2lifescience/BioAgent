"""Generic text generation helpers for LLM-backed tasks."""

from __future__ import annotations

from typing import Any

from .config import DEFAULT_AGENT_MODEL_KEY
from .llm_client import LLMClient


def generate_from_messages(
    messages: list[dict[str, Any]],
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.2,
    **kwargs: Any,
) -> str:
    """Generate text from chat messages using a configured model."""
    client = LLMClient(model_key=model_key)
    response = client.complete(
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature,
        **kwargs,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"Model '{model_key}' returned an empty response.")
    return str(content)


def generate_text(
    system_prompt: str,
    user_prompt: str,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    temperature: float = 0.2,
    **kwargs: Any,
) -> str:
    """Generate text from a system/user prompt pair."""
    return generate_from_messages(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model_key=model_key,
        temperature=temperature,
        **kwargs,
    )
