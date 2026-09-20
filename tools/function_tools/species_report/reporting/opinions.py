"""Concurrent reporting-agent opinions for species reports."""

from __future__ import annotations

import asyncio
from typing import Any

from models.config import DEFAULT_MODEL_KEYS, DEFAULT_MODELS
from models.openrouter_provider import OpenRouterProvider

from .agents import run_reporting_agent
from .prompts import build_model_opinion_messages


async def _collect_answers(
    species_name: str, question: str, model_keys: tuple[str, ...], agent_context: Any,
) -> dict[str, str]:
    async with OpenRouterProvider() as provider:
        async def run_one(model_key: str) -> str:
            try:
                messages = build_model_opinion_messages(
                    species_name=species_name, question=question,
                    model_label=str(DEFAULT_MODELS[model_key]["label"]),
                )
                return await run_reporting_agent(
                    messages, model_key, provider, temperature=0.2, agent_context=agent_context,
                )
            except Exception as exc:
                return f"Model call failed: {exc}"

        answers = await asyncio.gather(*(run_one(key) for key in model_keys))
    return dict(zip(model_keys, answers))


def collect_species_model_opinions(
    species_name: str,
    question: str,
    model_keys: list[str] | None = None,
    agent_context: Any = None,
) -> dict[str, Any]:
    """Synchronous workflow entry point, called from the tool's worker thread."""
    selected_model_keys = tuple(model_keys or DEFAULT_MODEL_KEYS)
    model_answers = asyncio.run(
        _collect_answers(species_name, question, selected_model_keys, agent_context)
    )
    return {
        "status": "ok",
        "species_name": species_name,
        "question": question,
        "model_keys": list(selected_model_keys),
        "model_answers": model_answers,
    }
