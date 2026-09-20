"""Factories for consistently configured OpenAI Agents SDK tools."""

from __future__ import annotations

from typing import Any

from agents import function_tool

from .guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL
from .results import tool_error


def bio_function_tool(*, timeout: int = 300, needs_approval: bool = False) -> Any:
    """Return the standard Pipeline2Agent FunctionTool decorator.

    Every public tool gets the same strict schema, error envelope, and
    boundary guardrails.  Callers only specify the timeout and whether an
    operation changes the workspace or executes a test command.
    """

    options: dict[str, Any] = {
        "strict_mode": True,
        "failure_error_function": tool_error,
        "tool_input_guardrails": [TOOL_INPUT_GUARDRAIL],
        "tool_output_guardrails": [TOOL_OUTPUT_GUARDRAIL],
        "timeout": timeout,
    }
    if needs_approval:
        options["needs_approval"] = True
    return function_tool(**options)


__all__ = ["bio_function_tool"]
