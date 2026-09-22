"""Agents exposed as callable tools through Agent.as_tool()."""

from agents import FunctionTool, Model

from .registry import SPECIALIST_BUILDERS, SPECIALIST_GROUPS, build_specialist_tools
from .reporting import build_report_review, build_report_synthesize
from .specialist import (
    build_coding,
    build_data_analysis,
    build_document,
    build_pipeline,
    build_research,
)



def build_agent_tools(model: Model | str) -> list[FunctionTool]:
    """Build model-backed agent tools for the root agent."""
    return [*build_specialist_tools(model), build_report_review(model), build_report_synthesize(model)]


__all__ = [
    "SPECIALIST_BUILDERS",
    "SPECIALIST_GROUPS",
    "build_agent_tools",
    "build_coding",
    "build_data_analysis",
    "build_document",
    "build_pipeline",
    "build_research",
    "build_specialist_tools",
    "build_report_review",
    "build_report_synthesize",
]
