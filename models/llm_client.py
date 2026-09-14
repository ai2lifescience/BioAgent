"""Compatibility wrapper around the OpenAI client configured for OpenRouter."""

from __future__ import annotations

from typing import Any

from .config import get_default_model, get_default_model_id
from .openrouter_client import create_client


class LLMClient:
    """Legacy-compatible direct client for non-agent report utilities."""

    def __init__(self, model_key: str) -> None:
        self.model_key = model_key
        self.model_config = get_default_model(model_key)
        self.model_id = get_default_model_id(model_key)
        self.model_label = str(self.model_config["label"])

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_choice: str | None = None, temperature: float = 0.1, **kwargs: Any) -> Any:
        request: dict[str, Any] = {"model": self.model_id, "messages": messages, "temperature": temperature, **kwargs}
        if tools is not None:
            request["tools"] = tools
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        with create_client() as client:
            return client.chat.completions.create(**request)
