"""Agents exposed as callable tools through Agent.as_tool()."""

from agents import FunctionTool, Model

from .pipeline_specialist import build_pipeline_specialist
from .registry import SPECIALIST_BUILDERS, SPECIALIST_GROUPS, build_specialist_tools
from .retrieval_specialist import build_retrieval_specialist
from .sequence_specialist import build_sequence_specialist


def build_agent_tools(model: Model | str) -> list[FunctionTool]:
    """Build model-backed agent tools for the root agent."""
    return build_specialist_tools(model)


__all__ = [
    "SPECIALIST_BUILDERS",
    "SPECIALIST_GROUPS",
    "build_agent_tools",
    "build_pipeline_specialist",
    "build_retrieval_specialist",
    "build_sequence_specialist",
    "build_specialist_tools",
]
