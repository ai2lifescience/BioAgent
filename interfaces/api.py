"""Programmatic API interface for BioAgent."""

from __future__ import annotations

from typing import Any, Callable

from harness.runtime import (
    ARTIFACT_STORE,
    delete_session,
    list_sessions,
    resume_bioagent,
    run_bioagent,
)
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS


def handle_request(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run BioAgent from application code."""
    return run_bioagent(request, session_id, model_key, max_skill_steps, log_fn)


def handle_approval(
    session_id: str,
    approved: bool,
    approval_id: str,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Approve or reject the pending SDK tool call for a session."""
    return resume_bioagent(session_id, approved, approval_id, log_fn=log_fn)


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
