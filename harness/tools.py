"""Expose BioAgent workflows as OpenAI Agents SDK function tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from agents import FunctionTool
from agents.tool_context import ToolContext

from registries.skill_registry import SKILL_DEFINITIONS

from .context import BioRunContext


async def _invoke(definition: Any, tool_context: ToolContext[Any], raw_input: str) -> str:
    context: BioRunContext = tool_context.context
    try:
        arguments = json.loads(raw_input or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")
    except (TypeError, json.JSONDecodeError, ValueError) as exc:
        result = {"error": str(exc), "error_type": type(exc).__name__}
        context.record("tool_finished", tool=definition.name, status="error", error=str(exc))
        return json.dumps(result, ensure_ascii=False)

    context.record("tool_started", tool=definition.name, arguments=arguments)
    skill_context = context.skill_context(definition.name, definition.tools)
    call_arguments = dict(arguments)
    call_arguments["context"] = skill_context
    handler = definition.handler
    if "log_fn" in inspect.signature(handler).parameters:
        call_arguments["log_fn"] = context.log

    try:
        result = await asyncio.to_thread(handler, **call_arguments)
        if not isinstance(result, dict):
            result = {"value": result}
        status = "error" if result.get("error") else "ok"
        record = {
            "skill": definition.name,
            "category": definition.category,
            "arguments": arguments,
            "result": result,
            "tool_calls": skill_context.tool_calls,
        }
        context.skill_results.append(record)
        if context.artifact_store is not None:
            context.artifact_store.register_result(context.session, record)
        context.record("tool_finished", tool=definition.name, status=status)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        error = {"error": str(exc), "error_type": type(exc).__name__}
        context.skill_results.append(
            {"skill": definition.name, "category": definition.category, "arguments": arguments, "result": error, "tool_calls": skill_context.tool_calls}
        )
        context.record("tool_finished", tool=definition.name, status="error", error=str(exc))
        return json.dumps(error, ensure_ascii=False)


def _needs_approval(definition: Any) -> bool:
    return False


def build_tools() -> list[FunctionTool]:
    """Build the complete high-level workflow tool set once per agent."""
    tools: list[FunctionTool] = []
    for definition in SKILL_DEFINITIONS:
        function = definition.skill_spec["function"]
        tools.append(
            FunctionTool(
                name=str(function["name"]),
                description=str(function.get("description") or definition.name),
                params_json_schema=dict(function.get("parameters") or {"type": "object"}),
                on_invoke_tool=lambda ctx, raw, definition=definition: _invoke(definition, ctx, raw),
                strict_json_schema=False,
                needs_approval=_needs_approval(definition),
            )
        )
    return tools
