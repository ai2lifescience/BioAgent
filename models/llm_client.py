"""LLM client helpers for BioAgent."""

from __future__ import annotations

import logging
import os
from typing import Any

from .config import (
    DEFAULT_OPENROUTER_API_BASE,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    configure_runtime_env,
    get_default_model,
    get_default_model_id,
)


def load_completion_function():
    configure_runtime_env()
    try:
        import litellm
        from litellm import completion
    except ModuleNotFoundError as exc:
        missing = exc.name or "required package"
        raise RuntimeError(
            f"Missing dependency '{missing}'. Install project dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    litellm.suppress_debug_info = True
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)
    logging.getLogger("litellm").setLevel(logging.ERROR)
    return completion


def provider_kwargs(model: str, model_config: dict[str, Any] | None = None) -> dict[str, str]:
    configure_runtime_env()
    config = model_config or {}
    api_base = config.get("api_base")
    if api_base:
        api_key = str(config.get("api_key") or "")
        if not api_key:
            raise RuntimeError(f"API key is required for model: {model}")
        return {
            "api_key": api_key,
            "api_base": str(api_base),
        }

    if model.startswith("openrouter/"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter models.")
        return {
            "api_key": api_key,
            "api_base": os.getenv("OPENROUTER_API_BASE", DEFAULT_OPENROUTER_API_BASE),
        }
    return {}


class LLMClient:
    """Thin LiteLLM wrapper used by the orchestrator."""

    def __init__(self, model_key: str) -> None:
        self.model_key = model_key
        self.model_config = get_default_model(model_key)
        self.model_id = get_default_model_id(model_key)
        self.model_label = str(self.model_config["label"])
        self.timeout_seconds = max(
            1.0,
            float(self.model_config.get("timeout_seconds", DEFAULT_LLM_TIMEOUT_SECONDS)),
        )
        self.supports_tool_calling = bool(self.model_config.get("supports_tool_calling", True))
        self._completion = load_completion_function()

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float = 0.1,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        request: dict[str, Any] = {
            "model": self.model_id,
            **provider_kwargs(self.model_id, self.model_config),
            "messages": messages,
            "temperature": temperature,
            "timeout": self.timeout_seconds if timeout is None else timeout,
            **kwargs,
        }
        if tools is not None:
            request["tools"] = tools
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        return self._completion(**request)

    def complete_without_tools(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> Any:
        """Request a normal model response without tool-call parameters."""
        return self.complete(
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
