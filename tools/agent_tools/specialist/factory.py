"""Shared construction for SDK agent-as-tool specialists."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agents import Agent, FunctionTool, Model, Tool
from agents import RunResult, RunResultStreaming

from harness.guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL
from harness.streaming import STREAM_SINK, nested_stream
from tools.infrastructure.tool_support.results import FunctionResult

from .contracts import SpecialistInput, SpecialistResult


def _specialist_input_builder(data: dict[str, Any]) -> str:
    """Give the nested agent a clear task while retaining typed outer input."""
    return str(data["params"]["task"])


async def _extract_specialist_result(result: RunResult | RunResultStreaming) -> str:
    """Normalize free-form nested prose into the common tool result envelope."""
    wrapper = result.context_wrapper
    summary = str(result.final_output or "").strip()
    if not summary:
        raise ValueError("The specialist returned an empty summary.")
    paths = []
    for item in wrapper.context.files:
        path = str(item.get("workspace_path") or item.get("path") or "").strip()
        if path and path not in paths:
            paths.append(path)
    data = wrapper.context.public({"summary": summary, "workspace_paths": paths})
    output = FunctionResult[SpecialistResult](
        status="ok", data=SpecialistResult.model_validate(data)
    )
    return output.model_dump_json()


def build_specialist(
    model: Model | str,
    *,
    name: str,
    description: str,
    instructions: str,
    tool_names: Iterable[str],
    available_tools: Iterable[Tool],
    max_turns: int,
    extra_tools: Iterable[FunctionTool] = (),
) -> FunctionTool:
    """Build one guarded specialist from a declarative tool-name set."""
    selected_names = frozenset(tool_names)
    selected = [tool for tool in available_tools if tool.name in selected_names]
    missing = selected_names - {tool.name for tool in selected}
    if missing:
        raise ValueError(f"Missing specialist tools: {sorted(missing)}")
    selected.extend(extra_tools)
    specialist = Agent(
        name=name,
        instructions=instructions,
        model=model,
        tools=selected,
        input_guardrails=[INPUT_GUARDRAIL],
        output_guardrails=[OUTPUT_GUARDRAIL],
    )
    return specialist.as_tool(
        tool_name=name,
        tool_description=description,
        parameters=SpecialistInput,
        input_builder=_specialist_input_builder,
        custom_output_extractor=_extract_specialist_result,
        max_turns=max_turns,
        # Agent.as_tool switches the nested run to streaming whenever this
        # callback is present. Match the caller's run mode at construction so
        # approval/resume state stays on the SDK's normal non-streaming path.
        on_stream=nested_stream if STREAM_SINK.get() is not None else None,
    )


__all__ = ["build_specialist"]
