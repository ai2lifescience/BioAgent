"""Notebook-friendly BioAgent helpers."""

from __future__ import annotations

from typing import Any, Callable

from interfaces.api import handle_request
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS


def run_bioagent(
    request: str,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run BioAgent from a notebook cell and return the full result dict."""
    return handle_request(
        request=request,
        model_key=model_key,
        max_skill_steps=max_skill_steps,
        log_fn=log_fn,
    )


def answer(request: str, **kwargs: Any) -> str:
    """Return only the answer text for quick notebook use."""
    return str(run_bioagent(request, **kwargs)["answer"])
