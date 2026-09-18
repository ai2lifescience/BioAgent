"""Application entry point for the single Agents SDK BioAgent runtime."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from agents import Model, Runner, RunConfig, RunState, SQLiteSession, ToolExecutionConfig
from agents.sandbox import SandboxRunConfig
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.tracing import gen_trace_id

from tools.common.evidence import EvidenceCollector
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_TURNS
from models.openrouter_provider import OpenRouterProvider

from .agent import create_agent
from .context import BioRunContext
from .sessions import SessionMetadata, SessionMetadataStore
from .sandbox import delete_workspace, list_files, open_workspace, prepare_run, session_root
from .tracing import BioAgentHooks, LOCAL_TRACES, configure_tracing


STATE_STORE = SessionMetadataStore()
SESSION_DB = Path(os.getenv("BIOAGENT_SESSION_DB", "runtime/agent_sessions.sqlite3"))

# SDK tracing stays local; each run supplies its own model provider.
configure_tracing()


def _approval_details(items: list[Any], context: BioRunContext | None = None) -> list[dict[str, Any]]:
    details = []
    for item in items:
        raw = item.raw_item
        raw = raw.model_dump() if hasattr(raw, "model_dump") else raw
        arguments = raw.get("action", {}) if raw.get("type") == "shell_call" else raw.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                pass
        detail = {
            "approval_id": uuid4().hex,
            "call_id": raw.get("call_id"),
            "agent": item.agent.name,
            "tool_name": item.tool_name,
            "arguments": arguments,
        }
        if item.tool_name == "pipeline_shell" and context and isinstance(arguments, dict):
            from tools.runtime_tools.pipeline_runtime.commands import parse_command
            from tools.runtime_tools.pipeline_runtime.store import JobStore
            try:
                args = parse_command(arguments["commands"][0])
                identifier = args.plan_id if args.operation == "run" else args.job_id
                detail["plan"] = JobStore(session_root(context.session_id)).get(identifier)["plan"]
            except (ValueError, KeyError, AttributeError, IndexError):
                pass
        details.append(detail)
    return details


async def async_run_bioagent(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_turns: int = DEFAULT_MAX_TURNS,
    log_fn: Callable[[str], None] | None = None,
    model: Model | None = None,
) -> dict[str, Any]:
    request = str(request or "").strip()
    if not request:
        raise ValueError("request is required")
    identifier = str(session_id or "").strip() or str(uuid4())
    async with STATE_STORE.async_locked_session(identifier, request) as (session, _created):
        if session.metadata.get("pending_run"):
            raise ValueError("Resolve the pending tool approval before sending another request in this session.")
        prepare_run(session)
        return await _execute(session, request, model_key, max_turns, log_fn, model)


async def async_resume_bioagent(
    session_id: str,
    approved: bool,
    approval_id: str,
    *,
    log_fn: Callable[[str], None] | None = None,
    model: Model | None = None,
) -> dict[str, Any]:
    """Apply an explicit decision to a saved SDK interruption and resume it."""
    identifier = str(session_id or "").strip()
    if not identifier or type(approved) is not bool or not approval_id:
        raise ValueError("session_id, approval_id, and a boolean approved decision are required")
    if STATE_STORE.get_session(identifier) is None:
        raise ValueError("No pending approval for this session.")
    async with STATE_STORE.async_locked_session(identifier) as (session, _created):
        pending = session.metadata.get("pending_run")
        if not pending:
            raise ValueError("No pending approval for this session.")
        matching = [i for i, item in enumerate(pending["approvals"]) if item["approval_id"] == approval_id]
        if len(matching) != 1:
            raise ValueError("Unknown or expired approval_id for this session.")
        return await _execute(
            session, pending["request"], pending["model_key"], pending["max_turns"],
            log_fn, model, pending=pending, decision=(matching[0], approved),
        )


async def _execute(
    session: SessionMetadata,
    request: str,
    model_key: str,
    max_turns: int,
    log_fn: Callable[[str], None] | None,
    model: Model | None,
    *,
    pending: dict[str, Any] | None = None,
    decision: tuple[int, bool] | None = None,
) -> dict[str, Any]:
    """Run or resume through the same SDK and result-collection path."""
    context = BioRunContext(
        session=session, model_key=model_key, log_fn=log_fn,
        tool_results=list(pending.get("tool_results", [])) if pending else [],
        events=list(pending.get("events", [])) if pending else [],
    )
    trace_id = pending["trace_id"] if pending else gen_trace_id()
    if not pending:
        context.record("run_started", request=request, model_key=model_key)
    session_db = Path(SESSION_DB)
    session_db.parent.mkdir(parents=True, exist_ok=True)
    sdk_session = SQLiteSession(session.session_id, db_path=session_db)
    provider = OpenRouterProvider()
    approvals: list[dict[str, Any]] = []
    snapshot = None
    LOCAL_TRACES.bind(trace_id, context)
    try:
        sandbox_root = session_root(session.session_id)
        agent = create_agent(
            model_key, model=model, sandbox_root=str(sandbox_root),
        )
        run_input: str | RunState = request
        if pending:
            # Restore agent definitions; this run resolves models through a fresh
            # provider instead of retaining clients from the approval pause.
            run_input = await RunState.from_json(
                agent, pending["state"], context_deserializer=lambda _data: context,
            )
            assert decision is not None
            index, approved = decision
            item = run_input.get_interruptions()[index]
            if approved:
                run_input.approve(item)
            else:
                run_input.reject(item, rejection_message="The user rejected this tool request.")
            context.record("approval_decision", approved=approved, tool_name=item.tool_name)
            # Consume the saved snapshot before execution. Failed or duplicate
            # requests must not replay already-executed side effects.
            session.metadata.pop("pending_run", None)
            STATE_STORE.save(session)
        async with open_workspace(session.session_id) as sandbox_session:
            context.sandbox_session = sandbox_session
            context.files = await list_files(sandbox_session)
            result = await Runner.run(
                agent, run_input, context=context, max_turns=max(1, int(max_turns)),
                hooks=BioAgentHooks(),
                run_config=RunConfig(
                    model_provider=provider,
                    workflow_name="BioAgent", trace_id=trace_id, group_id=session.session_id,
                    trace_include_sensitive_data=False,
                    tool_execution=ToolExecutionConfig(max_function_tool_concurrency=4),
                    sandbox=SandboxRunConfig(session=sandbox_session, cwd="."),
                ),
                session=sdk_session,
            )
            context.files = await list_files(sandbox_session)
        if result.interruptions:
            snapshot = result.to_state().to_json(context_serializer=lambda _context: {})
            approvals = _approval_details(result.interruptions, context)
            answer = "Review the requested tool arguments and approve or reject each pending call."
            status = "pending_approval"
        else:
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
        await provider.aclose()

    evidence = EvidenceCollector().collect(context.tool_results)
    if snapshot is not None:
        context.record("run_paused", reason="tool_approval", tool_names=[i["tool_name"] for i in approvals])
        session.metadata["pending_run"] = {
            "state": snapshot, "request": request, "model_key": model_key,
            "max_turns": max_turns, "trace_id": trace_id, "approvals": approvals,
            "tool_results": context.tool_results, "events": context.events,
        }
    else:
        context.record("run_finished", status=status, tool_count=len(context.tool_results))
        # Pauses are not additional conversational exchanges.
        STATE_STORE.record_exchange(session, request, answer)
    run = dict(session.metadata.get("run") or {})
    return {
        "answer": answer, "status": status, "approval_required": bool(approvals),
        "approvals": approvals, "session_id": session.session_id,
        "messages": [{"role": "user", "content": request}, {"role": "assistant", "content": answer}],
        "evidence": evidence, "trace": context.events,
        "run": run, "files": context.files,
        "runtime": "agents_sdk", "model_key": model_key,
    }


def run_bioagent(
    request: str,
    session_id: str | None = None,
    model_key: str = DEFAULT_AGENT_MODEL_KEY,
    max_turns: int = DEFAULT_MAX_TURNS,
    log_fn: Callable[[str], None] | None = None,
    model: Model | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for CLI, HTTP, and notebook callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_run_bioagent(request, session_id, model_key, max_turns, log_fn, model))
    raise RuntimeError("An event loop is already running; await async_run_bioagent instead.")


def resume_bioagent(
    session_id: str, approved: bool, approval_id: str, *,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for :func:`async_resume_bioagent`."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_resume_bioagent(session_id, approved, approval_id, log_fn=log_fn))
    raise RuntimeError("An event loop is already running; await async_resume_bioagent instead.")


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
    deleted = STATE_STORE.delete_session(identifier)
    try:
        delete_workspace(identifier)
    except (FileNotFoundError, ValueError):
        pass
    return deleted


async def async_list_sessions() -> list[dict[str, Any]]:
    """List metadata with message counts read from the SDK session store."""
    sessions = STATE_STORE.list_sessions()
    if not Path(SESSION_DB).exists():
        for item in sessions:
            item["message_count"] = 0
        return sessions

    for item in sessions:
        sdk_session = SQLiteSession(item["session_id"], db_path=SESSION_DB)
        try:
            history = await sdk_session.get_items()
        finally:
            sdk_session.close()
        item["message_count"] = sum(
            isinstance(entry, dict) and entry.get("role") in {"user", "assistant"}
            for entry in history
        )
    return sessions


def list_sessions() -> list[dict[str, Any]]:
    """Synchronous wrapper for :func:`async_list_sessions`."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_list_sessions())
    raise RuntimeError("An event loop is already running; await async_list_sessions instead.")
