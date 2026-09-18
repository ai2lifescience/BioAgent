"""Assemble the complete tool surface supplied to the root SDK Agent.

This is the application-level registry.  The narrower
``tools.agent_tools.registry`` only assembles nested specialists; keeping the
two boundaries explicit prevents specialist construction from being mixed
with function, hosted, or runtime tool registration.
"""

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
