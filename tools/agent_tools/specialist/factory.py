"""Shared construction for SDK agent-as-tool specialists."""

from __future__ import annotations

from collections.abc import Iterable

from agents import Agent, FunctionTool, Model

from harness.guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL


def build_specialist(
    model: Model | str,
    *,
    name: str,
    description: str,
    instructions: str,
    tool_names: Iterable[str],
    available_tools: Iterable[FunctionTool],
    max_turns: int,
) -> FunctionTool:
    """Build one guarded specialist from a declarative tool-name set."""
    selected_names = frozenset(tool_names)
    specialist = Agent(
        name=name,
        instructions=instructions,
        model=model,
        tools=[tool for tool in available_tools if tool.name in selected_names],
        input_guardrails=[INPUT_GUARDRAIL],
        output_guardrails=[OUTPUT_GUARDRAIL],
    )
    return specialist.as_tool(tool_name=name, tool_description=description, max_turns=max_turns)


__all__ = ["build_specialist"]
