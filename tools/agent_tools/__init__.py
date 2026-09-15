"""Agents exposed as callable tools through Agent.as_tool()."""

from .specialists import SPECIALIST_GROUPS, build_specialist_tools


def build_agent_tools(model):
    """Build model-backed agent tools for the root agent."""
    return build_specialist_tools(model)


__all__ = ["SPECIALIST_GROUPS", "build_agent_tools", "build_specialist_tools"]
