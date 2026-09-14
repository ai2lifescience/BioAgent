"""Application entry point for the single Agents SDK BioAgent runtime."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from agents import Model, Runner, RunConfig, SQLiteSession, set_default_openai_api
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.tracing import gen_trace_id

from harness.support.artifacts import SessionArtifactStore
from harness.support.evidence import EvidenceCollector
from harness.support.verifier import Verifier
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS
from models.openrouter_client import create_async_client

from .agent import create_agent
from .context import BioRunContext
from .sessions import SessionMetadataStore
from .tracing import BioAgentHooks, LOCAL_TRACES, configure_tracing


STATE_STORE = SessionMetadataStore()
ARTIFACT_STORE = SessionArtifactStore(STATE_STORE)
SESSION_DB = Path(os.getenv("BIOAGENT_SESSION_DB", "runtime/agent_sessions.sqlite3"))

# OpenRouter exposes the OpenAI-compatible Chat Completions API. SDK tracing
# remains available through local hooks; the default OpenAI exporter is off.
set_default_openai_api("chat_completions")
configure_tracing()


def _session_id(value: str | None) -> str:
    return str(value or "").strip() or str(uuid4())


async def async_run_bioagent(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
    log_fn: Callable[[str], None] | None = None,
    model: Model | None = None,
) -> dict[str, Any]:
    request = str(request or "").strip()
    if not request:
        raise ValueError("request is required")
    resolved_session_id = _session_id(session_id)
    async with STATE_STORE.async_locked_session(resolved_session_id, request) as (session, _created):
        ARTIFACT_STORE.prepare_run(session)
        context = BioRunContext(session=session, model_key=model_key, artifact_store=ARTIFACT_STORE, log_fn=log_fn)
        context.record("run_started", request=request, model_key=model_key)
        session_db = Path(SESSION_DB)
        session_db.parent.mkdir(parents=True, exist_ok=True)
        sdk_session = SQLiteSession(resolved_session_id, db_path=session_db)
        client = None
        trace_id = gen_trace_id()
        LOCAL_TRACES.bind(trace_id, context)
        try:
            client = create_async_client() if model is None else None
            agent = create_agent(model_key, model=model, client=client)
            result = await Runner.run(
                agent,
                request,
                context=context,
                max_turns=max(1, int(max_skill_steps)),
                hooks=BioAgentHooks(),
                run_config=RunConfig(
                    workflow_name="BioAgent",
                    trace_id=trace_id,
                    group_id=resolved_session_id,
                    trace_include_sensitive_data=False,
                ),
                session=sdk_session,
            )
            answer = str(result.final_output or "")
            status = "ok"
        except InputGuardrailTripwireTriggered:
            answer = (
                "I can’t help with actionable biological procedures that could increase "
                "pathogen harm. I can provide safe, high-level background or discuss "
                "defensive biosafety considerations."
            )
            status = "blocked"
            context.record("run_blocked", reason="input_guardrail")
        except Exception as exc:
            answer = f"Agent run failed: {exc}"
            status = "error"
            context.record("run_failed", error=str(exc), error_type=type(exc).__name__)
        finally:
            LOCAL_TRACES.unbind(trace_id)
            sdk_session.close()
            if client is not None:
                await client.close()

        for record in context.skill_results:
            ARTIFACT_STORE.register_result(session, record)
        evidence = EvidenceCollector().collect(context.skill_results)
        verification = Verifier().verify(
            user_request=request,
            skill_results=context.skill_results,
            evidence=evidence,
            allow_model_knowledge=not context.skill_results,
            answer=answer,
        )
        if status == "error":
            verification["status"] = "error"
            verification.setdefault("errors", []).append(answer)
        elif status == "blocked":
            verification["status"] = "blocked"
            verification.setdefault("warnings", []).append("Input guardrail blocked the request.")
        context.record("run_finished", status=status, skill_count=len(context.skill_results))
        run = dict(session.metadata.get("run") or {})
        STATE_STORE.record_exchange(session, request, answer)
        return {
            "answer": answer,
            "session_id": session.session_id,
            "messages": [{"role": "user", "content": request}, {"role": "assistant", "content": answer}],
            "evidence": evidence,
            "verification": verification,
            "trace": context.events,
            "run": run,
            "artifacts": ARTIFACT_STORE.for_run(session, run.get("run_id")),
            "runtime": "agents_sdk",
            "model_key": model_key,
        }


def run_bioagent(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_skill_steps: int = DEFAULT_MAX_SKILL_STEPS,
    log_fn: Callable[[str], None] | None = None,
    model: Model | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for CLI, HTTP, and notebook callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_run_bioagent(request, session_id, model_key, max_skill_steps, log_fn, model))
    raise RuntimeError("An event loop is already running; await async_run_bioagent instead.")


def delete_session(session_id: str) -> bool:
    """Delete SDK conversation history and application metadata together."""
    identifier = str(session_id or "").strip()
    if not identifier:
        return False
    session_db = Path(SESSION_DB)
    session_db.parent.mkdir(parents=True, exist_ok=True)
    sdk_session = SQLiteSession(identifier, db_path=session_db)
    try:
        asyncio.run(sdk_session.clear_session())
    finally:
        sdk_session.close()
    return STATE_STORE.delete_session(identifier)


def list_sessions() -> list[dict[str, Any]]:
    return STATE_STORE.list_sessions()
