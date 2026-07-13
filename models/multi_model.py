"""Generic multi-model prompt execution helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .config import DEFAULT_MODEL_KEYS, DEFAULT_MODELS
from .text_generation import generate_from_messages, generate_text

MessageBuilder = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


def run_multi_model_messages(
    message_builder: MessageBuilder,
    model_keys: list[str] | tuple[str, ...] | None = None,
    temperature: float = 0.2,
) -> dict[str, str]:
    """Run model-specific messages against multiple configured models."""
    selected_model_keys = tuple(model_keys or DEFAULT_MODEL_KEYS)
    if not selected_model_keys:
        return {}

    def _run_one(model_key: str) -> str:
        config = DEFAULT_MODELS[model_key]
        return generate_from_messages(
            messages=message_builder(model_key, config),
            model_key=model_key,
            temperature=temperature,
        )

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(selected_model_keys)) as executor:
        future_to_key = {
            executor.submit(_run_one, model_key): model_key
            for model_key in selected_model_keys
        }
        for future in as_completed(future_to_key):
            model_key = future_to_key[future]
            try:
                results[model_key] = future.result()
            except Exception as exc:
                results[model_key] = f"Model call failed: {exc}"
    return results


def run_multi_model_prompt(
    system_prompt: str,
    user_prompt: str,
    model_keys: list[str] | tuple[str, ...] | None = None,
    temperature: float = 0.2,
) -> dict[str, str]:
    """Run the same system/user prompt pair against multiple configured models."""
    selected_model_keys = tuple(model_keys or DEFAULT_MODEL_KEYS)
    if not selected_model_keys:
        return {}

    def _run_one(model_key: str) -> str:
        return generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_key=model_key,
            temperature=temperature,
        )

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(selected_model_keys)) as executor:
        future_to_key = {
            executor.submit(_run_one, model_key): model_key
            for model_key in selected_model_keys
        }
        for future in as_completed(future_to_key):
            model_key = future_to_key[future]
            try:
                results[model_key] = future.result()
            except Exception as exc:
                results[model_key] = f"Model call failed: {exc}"
    return results
