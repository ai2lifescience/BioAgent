"""Assemble the tool surface supplied to the root Agents SDK Agent."""

from agents import Model

from .agent_tools import build_agent_tools
from .function_tools import FUNCTION_TOOLS
from .hosted_tools import HOSTED_TOOLS
from .runtime_tools import RUNTIME_TOOLS


def build_all_tools(model: Model | str):
    """Return all enabled SDK tool categories for one root agent."""
    return [
        *FUNCTION_TOOLS,
        *build_agent_tools(model),
        *HOSTED_TOOLS,
        *RUNTIME_TOOLS,
    ]


__all__ = ["build_all_tools"]
