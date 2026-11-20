"""Assemble the complete tool surface supplied to the root SDK Agent.

This is the application-level registry.  The narrower
``tools.agent_tools.registry`` only assembles nested specialists; keeping the
two boundaries explicit prevents specialist construction from being mixed
with function or hosted tool registration.
"""

from agents import Model

from .agent_tools import build_agent_tools
from .function_tools import FUNCTION_TOOLS
from .hosted_tools import HOSTED_TOOLS


def build_all_tools(model: Model | str):
    """Return all enabled SDK tool categories for one root agent."""
    from isolation import isolated_execution, ISOLATED_TOOLS, SPECIALISTS
    if isolated_execution():
        from tools.function_tools.website import WEBSITE_TOOLS
        return [
            *[tool for tool in FUNCTION_TOOLS if tool.name in ISOLATED_TOOLS],
            *[tool for tool in build_agent_tools(model) if tool.name in SPECIALISTS | {'pipeline_specialist'}],
            *WEBSITE_TOOLS,
        ]
    return [
        *FUNCTION_TOOLS,
        *build_agent_tools(model),
        *HOSTED_TOOLS,
    ]


__all__ = ["build_all_tools"]
