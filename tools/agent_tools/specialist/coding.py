"""Coding-workspace specialist agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from tools.function_tools import FUNCTION_TOOLS

from .factory import build_specialist

NAME = "coding_specialist"
DESCRIPTION = "Inspect and improve workspace code with explicit approval for edits and tests."
INSTRUCTIONS = (
    "Work in the active workspace only. Inspect or search before proposing a change, "
    "use code_edit only for a complete, reviewable file replacement, and use code_test "
    "only with one of its bounded commands. Explain the intended change, preserve the "
    "expected hash when editing, and wait for runtime approval for writes or tests."
)
TOOL_NAMES = frozenset({"code_inspection", "code_edit", "code_test"})


def build_coding(model: Model | str) -> FunctionTool:
    return build_specialist(
        model, name=NAME, description=DESCRIPTION, instructions=INSTRUCTIONS,
        tool_names=TOOL_NAMES, available_tools=FUNCTION_TOOLS, max_turns=8,
    )
