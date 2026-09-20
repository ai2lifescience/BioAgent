"""Retrieval-domain specialist agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from tools.function_tools import FUNCTION_TOOLS

from .factory import build_specialist


NAME = "retrieval_specialist"
DESCRIPTION = (
    "Coordinate a task combining at least two of ncbi_retrieval, database_lookup, "
    "alphafold_download, and species_report, or an explicit request for this specialist. "
    "A single retrieval, metadata query, structure download, or cited species report "
    "belongs to its direct tool."
)
INSTRUCTIONS = (
    "Carry out the delegated retrieval or research task using the registered NCBI, "
    "database, download, and report tools. Use source records for record requests and "
    "species_report for cited synthesis. Preserve citations and downloaded paths; "
    "report missing inputs or failures."
)
TOOL_NAMES = frozenset({"ncbi_retrieval", "database_lookup", "alphafold_download", "species_report"})


def build_retrieval(model: Model | str) -> FunctionTool:
    """Build the retrieval-domain agent as a callable SDK tool."""
    return build_specialist(
        model,
        name=NAME,
        description=DESCRIPTION,
        instructions=INSTRUCTIONS,
        tool_names=TOOL_NAMES,
        available_tools=FUNCTION_TOOLS,
        max_turns=4,
    )
