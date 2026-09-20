"""Markdown synthesis service for species reports."""

from __future__ import annotations

import asyncio
from typing import Any

from models.config import DEFAULT_MODEL_KEYS, DEFAULT_MODELS, DEFAULT_SYNTHESIS_MODEL_KEY
from models.openrouter_provider import OpenRouterProvider

from .agents import run_reporting_agent
from .prompts import build_report_synthesis_messages


async def _synthesize(
    messages: list[dict[str, Any]], candidate_keys: list[str], agent_context: Any,
) -> tuple[str, str]:
    errors: list[str] = []
    async with OpenRouterProvider() as provider:
        for candidate_key in candidate_keys:
            if candidate_key not in DEFAULT_MODELS:
                continue
            try:
                markdown = await run_reporting_agent(
                    messages, candidate_key, provider, temperature=0.15, agent_context=agent_context,
                )
                return candidate_key, markdown
            except Exception as exc:
                errors.append(f"{candidate_key}: {exc}")
    raise RuntimeError("All report synthesis models failed:\n" + "\n".join(errors))


def synthesize_species_markdown_report(
    species_name: str,
    question: str,
    model_answers: dict[str, str],
    sources: list[dict[str, Any]],
    retrieval_context: str | None = None,
    model_key: str | None = None,
    agent_context: Any = None,
) -> dict[str, Any]:
    """Synchronous workflow entry point with sequential model fallback."""
    model_labels = {
        key: str(config["label"])
        for key, config in DEFAULT_MODELS.items()
    }
    messages = build_report_synthesis_messages(
        species_name=species_name,
        question=question,
        retrieval_context=retrieval_context or "",
        model_answers=model_answers,
        sources=sources,
        model_labels=model_labels,
    )
    candidate_keys = [
        model_key or DEFAULT_SYNTHESIS_MODEL_KEY,
        *[
            key
            for key in DEFAULT_MODEL_KEYS
            if key != (model_key or DEFAULT_SYNTHESIS_MODEL_KEY)
        ],
    ]
    selected_key, markdown = asyncio.run(_synthesize(messages, candidate_keys, agent_context))
    return {
        "status": "ok",
        "species_name": species_name,
        "question": question,
        "model_key": selected_key,
        "markdown": markdown,
    }
