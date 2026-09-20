"""Agents exposed as callable tools through Agent.as_tool()."""

from agents import FunctionTool, Model

from .registry import SPECIALIST_BUILDERS, SPECIALIST_GROUPS, build_specialist_tools
from .specialist import (
    build_coding,
    build_data_analysis,
    build_document,
    build_pipeline,
    build_retrieval,
    build_biology,
    build_web_research,
)

# Stable public aliases for callers that already use the SDK tool-oriented
# names. New code can use the shorter builders above.
build_coding_specialist = build_coding
build_data_analysis_specialist = build_data_analysis
build_document_specialist = build_document
build_pipeline_specialist = build_pipeline
build_retrieval_specialist = build_retrieval
build_biology_specialist = build_biology
build_web_research_specialist = build_web_research


def build_agent_tools(model: Model | str) -> list[FunctionTool]:
    """Build model-backed agent tools for the root agent."""
    return build_specialist_tools(model)


__all__ = [
    "SPECIALIST_BUILDERS",
    "SPECIALIST_GROUPS",
    "build_agent_tools",
    "build_pipeline_specialist",
    "build_coding_specialist",
    "build_data_analysis_specialist",
    "build_document_specialist",
    "build_retrieval_specialist",
    "build_biology_specialist",
    "build_web_research_specialist",
    "build_coding",
    "build_data_analysis",
    "build_document",
    "build_pipeline",
    "build_retrieval",
    "build_biology",
    "build_web_research",
    "build_specialist_tools",
]
