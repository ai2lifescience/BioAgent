"""Notebook-friendly BioAgent helpers."""

from __future__ import annotations

from typing import Any, Callable

from interfaces.api import handle_request
from harness.runtime import async_run_bioagent, async_resume_bioagent, resume_bioagent
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_TURNS


def run_bioagent(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_turns: int = DEFAULT_MAX_TURNS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run BioAgent from a notebook cell and return the full result dict."""
    return handle_request(
        request=request,
        session_id=session_id,
        model_key=model_key,
        max_turns=max_turns,
        log_fn=log_fn,
    )


def answer(request: str, **kwargs: Any) -> str:
    """Return only the answer text for quick notebook use."""
    return str(run_bioagent(request, **kwargs)["answer"])


async def arun_bioagent(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_turns: int = DEFAULT_MAX_TURNS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Async helper for notebooks with an active event loop."""
    return await async_run_bioagent(request, session_id, model_key, max_turns, log_fn)
