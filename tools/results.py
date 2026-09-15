"""Typed tool results and application evidence capture around ordinary functions.

The SDK decorator owns schemas, input validation, invocation and failures. This
module only formats BioAgent output and records artifacts/evidence for the UI.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Literal, TYPE_CHECKING

from agents import RunContextWrapper
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from harness.context import BioRunContext


class ToolError(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str
    message: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['ok', 'error', 'blocked']
    data: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
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
    artifacts = data.pop('artifacts', [])
    evidence = data.pop('evidence', [])
    return ToolResult(
        status='error' if failed else ('blocked' if state == 'blocked' else 'ok'),
        data=data,
        artifacts=artifacts if isinstance(artifacts, list) else [],
        evidence=evidence if isinstance(evidence, list) else [],
        error=ToolError(code=str(code), message=str(message or 'Tool execution failed.')) if failed else None,
    )


def tool_error(ctx: RunContextWrapper[Any], error: Exception) -> str:
    """SDK failure formatter, including malformed model arguments."""
    result = {'error': str(error), 'error_type': type(error).__name__}
    context = ctx.context
    name = getattr(ctx, 'tool_name', 'unknown_tool')
    if hasattr(context, 'skill_results'):
        context.skill_results.append({'skill': name, 'arguments': {}, 'result': result, 'tool_calls': []})
        context.record('tool_failed', tool=name, error_type=type(error).__name__)
    return result_envelope(result).model_dump_json()


async def run_workflow(
    context: BioRunContext,
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
    record = {'skill': name, 'category': category, 'arguments': arguments,
              'result': result, 'tool_calls': workflow_context.action_calls}
    context.skill_results.append(record)
    envelope = result_envelope(result)
    if context.artifact_store is not None:
        context.artifact_store.register_result(context.session, record)
        envelope.artifacts = context.artifact_store.for_run(context.session, context.run.get('run_id'))
    from harness.support.evidence import EvidenceCollector
    envelope.evidence = EvidenceCollector().collect([record])['citations']
    context.record('tool_finished', tool=name, status=envelope.status)
    return envelope.model_dump_json()
