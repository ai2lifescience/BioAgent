"""Biology-domain specialist agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from tools.function_tools import FUNCTION_TOOLS

from .factory import build_specialist


NAME = "biology_specialist"
DESCRIPTION = (
    "Coordinate a task needing at least two of biology_analysis, sequence_analysis, genome_map, "
    "blast_search, and protein_structure_analysis, or an explicit request for "
    "this specialist. For one Biopython operation, sequence metric, map, "
    "similarity search, or structure analysis, choose the direct tool."
)
INSTRUCTIONS = (
    "Carry out the delegated basic-biology transformation, sequence-metrics, genome-map, BLAST, or "
    "structure-analysis task using the smallest necessary set of registered "
    "biology tools. Follow "
    "dependencies: wait for a required input before starting the next operation. "
    "Return results, evidence, and artifact paths; report missing inputs or failures."
)
TOOL_NAMES = frozenset({
    "biology_analysis", "sequence_analysis", "genome_map", "blast_search", "protein_structure_analysis",
})


def build_biology(model: Model | str) -> FunctionTool:
    """Build the biology-domain agent as a callable SDK tool."""
    return build_specialist(
        model,
        name=NAME,
        description=DESCRIPTION,
        instructions=INSTRUCTIONS,
        tool_names=TOOL_NAMES,
        available_tools=FUNCTION_TOOLS,
        max_turns=4,
    )
