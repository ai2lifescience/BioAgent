"""Data-analysis specialist agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from tools.function_tools import FUNCTION_TOOLS

from .factory import build_specialist

NAME = "data_analysis_specialist"
DESCRIPTION = "Profile, summarize, group, and visualize uploaded tabular data with bounded operations."
INSTRUCTIONS = (
    "Analyze supplied CSV, TSV, or Excel workspace files with table_profile, table_group, and table_plot. Start by "
    "profiling when the schema is unknown, choose columns from actual tool output, and "
    "return measured values and plot paths. Do not execute arbitrary Python or invent "
    "rows, columns, or metrics."
)
TOOL_NAMES = frozenset({"table_profile", "table_group", "table_plot", "file_inspection", "workspace_search"})


def build_data_analysis(model: Model | str) -> FunctionTool:
    return build_specialist(
        model, name=NAME, description=DESCRIPTION, instructions=INSTRUCTIONS,
        tool_names=TOOL_NAMES, available_tools=FUNCTION_TOOLS, max_turns=6,
    )
