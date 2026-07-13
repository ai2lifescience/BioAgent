"""Programmatic API interface for BioAgent."""

from __future__ import annotations

from typing import Any, Callable

from agent_core import BioAgentOrchestrator
from agent_core.artifacts import SessionArtifactStore
from agent_core.memory import InMemoryStateStore
from agent_core.trace import InMemoryTraceStore
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS


STATE_STORE = InMemoryStateStore()
TRACE_STORE = InMemoryTraceStore()
ARTIFACT_STORE = SessionArtifactStore(STATE_STORE)
ORCHESTRATOR = BioAgentOrchestrator(
    memory=STATE_STORE,
    trace_store=TRACE_STORE,
    artifact_store=ARTIFACT_STORE,
)


def handle_request(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run BioAgent from application code."""
    return ORCHESTRATOR.run(
        user_request=request,
        session_id=session_id,
        model_key=model_key,
        max_skill_steps=max_skill_steps,
        log_fn=log_fn,
    )


def list_sessions() -> list[dict[str, Any]]:
    """List in-memory chat sessions for app-scoped interfaces."""
    return STATE_STORE.list_sessions()


def delete_session(session_id: str) -> bool:
    """Delete one in-memory chat session."""
    return STATE_STORE.delete_session(session_id)


def store_upload(
    session_id: str | None,
    filename: str,
    data: bytes,
    content_type: str = "",
) -> dict[str, Any]:
    """Store one uploaded file in a chat session."""
    return ARTIFACT_STORE.store_upload(
        session_id=session_id,
        filename=filename,
        data=data,
        content_type=content_type,
    )


def list_uploads(session_id: str | None) -> dict[str, Any]:
    """List uploaded files for one chat session."""
    return ARTIFACT_STORE.list_uploads(session_id)


def delete_upload(session_id: str, upload_id_or_artifact_id: str) -> bool:
    """Delete one uploaded file from a chat session."""
    return ARTIFACT_STORE.delete_upload(
        session_id=session_id,
        upload_id_or_artifact_id=upload_id_or_artifact_id,
    )
