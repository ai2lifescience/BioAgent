"""Direct model-opinion service for species reports."""

from __future__ import annotations

from typing import Any

from models.config import DEFAULT_MODEL_KEYS
from models.multi_model import run_multi_model_messages

from .prompts import build_model_opinion_messages


def collect_species_model_opinions(
    species_name: str,
    question: str,
    model_keys: list[str] | None = None,
) -> dict[str, Any]:
    selected_model_keys = tuple(model_keys or DEFAULT_MODEL_KEYS)

    def _messages(_model_key: str, config: dict[str, Any]) -> list[dict[str, str]]:
        return build_model_opinion_messages(
            species_name=species_name,
            question=question,
            model_label=str(config["label"]),
        )

    model_answers = run_multi_model_messages(
        message_builder=_messages,
        model_keys=selected_model_keys,
        temperature=0.2,
    )
    return {
        "status": "ok",
        "species_name": species_name,
        "question": question,
        "model_keys": list(selected_model_keys),
        "model_answers": model_answers,
    }

