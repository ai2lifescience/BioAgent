"""Generic text generation helpers for LLM-backed tasks."""

from __future__ import annotations

from typing import Any

from .config import DEFAULT_AGENT_MODEL_KEY, get_default_model_id
from .openrouter_client import create_client


def generate_from_messages(
    messages: list[dict[str, Any]],
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.2,
    **kwargs: Any,
) -> str:
    """Generate text from chat messages using a configured model."""
    request: dict[str, Any] = {
        "model": get_default_model_id(model_key),
        "messages": messages,
        "temperature": temperature,
        **kwargs,
    }
    if tools is not None:
        request["tools"] = tools
    if tool_choice is not None:
        request["tool_choice"] = tool_choice
    with create_client() as client:
        response = client.chat.completions.create(**request)
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
