"""Markdown synthesis service for species reports."""

from __future__ import annotations

from typing import Any

from models.config import DEFAULT_MODEL_KEYS, DEFAULT_MODELS, DEFAULT_SYNTHESIS_MODEL_KEY
from models.text_generation import generate_from_messages

from .prompts import build_report_synthesis_messages


def synthesize_species_markdown_report(
    species_name: str,
    question: str,
    model_answers: dict[str, str],
    sources: list[dict[str, Any]],
    retrieval_context: str | None = None,
    model_key: str | None = None,
) -> dict[str, Any]:
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
    errors: list[str] = []
    for candidate_key in candidate_keys:
        if candidate_key not in DEFAULT_MODELS:
            continue
        try:
            markdown = generate_from_messages(
                messages=messages,
                model_key=candidate_key,
                temperature=0.15,
            )
            return {
                "status": "ok",
                "species_name": species_name,
                "question": question,
                "model_key": candidate_key,
                "markdown": markdown,
            }
        except Exception as exc:
            errors.append(f"{candidate_key}: {exc}")
    raise RuntimeError("All report synthesis models failed:\n" + "\n".join(errors))
