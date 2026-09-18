"""Retrieval-domain specialist agent."""

from __future__ import annotations

from agents import Agent, FunctionTool, Model

from harness.guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL
from tools.function_tools import FUNCTION_TOOLS


NAME = "retrieval_specialist"
DESCRIPTION = (
    "Coordinate a task combining at least two of ncbi_retrieval, database_lookup, "
    "and species_report, or an explicit request for this specialist. A single "
    "NCBI download, database query, or cited species report belongs to its direct tool."
)
INSTRUCTIONS = (
    "Carry out the delegated retrieval or research task using the registered NCBI, "
    "database, and report tools. Use source records for record requests and "
    "species_report for cited synthesis. Preserve citations and downloaded paths; "
    "report missing inputs or failures."
)
TOOL_NAMES = frozenset({"ncbi_retrieval", "database_lookup", "species_report"})


def build_retrieval_specialist(model: Model | str) -> FunctionTool:
    """Build the retrieval-domain agent as a callable SDK tool."""
    specialist = Agent(
        name=NAME,
        instructions=INSTRUCTIONS,
        model=model,
        tools=[tool for tool in FUNCTION_TOOLS if tool.name in TOOL_NAMES],
        input_guardrails=[INPUT_GUARDRAIL],
        output_guardrails=[OUTPUT_GUARDRAIL],
    )
    return specialist.as_tool(tool_name=NAME, tool_description=DESCRIPTION, max_turns=4)
