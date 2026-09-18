"""Typed tool results and application evidence capture around ordinary functions.

The SDK decorator owns schemas, input validation, invocation and failures. This
module only formats Pipeline2Agent output and records files/evidence for the UI.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Literal, TYPE_CHECKING

from agents import RunContextWrapper
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from harness.context import AgentRunContext


class ToolError(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str
    message: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['ok', 'error', 'blocked']
    data: dict[str, Any] = Field(default_factory=dict)
    files: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    error: ToolError | None = None


def result_envelope(value: dict[str, Any]) -> ToolResult:
    data = dict(value)
    state = data.pop('status', 'ok')
    message = data.pop('error', None)
    code = data.pop('error_type', 'TOOL_ERROR')
    failed = bool(message) or state == 'error'
    if state not in ('ok', 'error', 'blocked'):
        data['state'] = state
    files = data.pop('files', [])
    evidence = data.pop('evidence', [])
    return ToolResult(
        status='error' if failed else ('blocked' if state == 'blocked' else 'ok'),
        data=data,
        files=files if isinstance(files, list) else [],
        evidence=evidence if isinstance(evidence, list) else [],
        error=ToolError(code=str(code), message=str(message or 'Tool execution failed.')) if failed else None,
    )


def tool_error(ctx: RunContextWrapper[Any], error: Exception) -> str:
    """SDK failure formatter, including malformed model arguments."""
    result = {'error': str(error), 'error_type': type(error).__name__}
    context = ctx.context
    name = getattr(ctx, 'tool_name', 'unknown_tool')
    if hasattr(context, 'tool_results'):
        context.tool_results.append({'tool': name, 'arguments': {}, 'result': result, 'tool_calls': []})
        context.record('tool_failed', tool=name, error_type=type(error).__name__)
    return result_envelope(result).model_dump_json()


async def run_workflow(
    context: AgentRunContext,
    name: str,
    handler: Callable[..., dict[str, Any]],
    arguments: dict[str, Any],
    *,
    category: str,
    with_progress: bool = False,
) -> str:
    workflow_context = context.workflow_context(name)
    kwargs = {**arguments, 'context': workflow_context}
    if with_progress:
        kwargs['log_fn'] = context.log
    context.record('tool_started', tool=name)
    try:
        result = await asyncio.to_thread(handler, **kwargs)
    except Exception as exc:
        result = {'error': str(exc), 'error_type': type(exc).__name__}
    record = {'workflow': name, 'category': category, 'arguments': arguments,
              'result': result, 'tool_calls': workflow_context.action_calls}
    context.tool_results.append(record)
    envelope = result_envelope(result)
    if getattr(context, "sandbox_session", None) is not None:
        from harness.sandbox import list_files
        context.files = await list_files(context.sandbox_session)
        envelope.files = context.files
    from tools.common.evidence import EvidenceCollector
    envelope.evidence = EvidenceCollector().collect([record])['citations']
    context.record('tool_finished', tool=name, status=envelope.status)
    return envelope.model_dump_json()
