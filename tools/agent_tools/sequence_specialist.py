"""Sequence-domain specialist agent."""

from __future__ import annotations

from agents import Agent, FunctionTool, Model

from harness.guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL
from tools.function_tools import FUNCTION_TOOLS


NAME = "sequence_specialist"
DESCRIPTION = (
    "Coordinate a task needing at least two of sequence_analysis, genome_map, "
    "blast_search, and protein_structure_analysis, or an explicit request for "
    "this specialist. For a single sequence metric, map, similarity search, "
    "or structure analysis, choose that direct tool."
)
INSTRUCTIONS = (
    "Carry out the delegated sequence, genome-map, BLAST, or structure-analysis "
    "task using the smallest necessary set of registered tools. Follow "
    "dependencies: wait for a required input before starting the next operation. "
    "Return results, evidence, and artifact paths; report missing inputs or failures."
)
TOOL_NAMES = frozenset({
    "sequence_analysis", "genome_map", "blast_search", "protein_structure_analysis",
})


def build_sequence_specialist(model: Model | str) -> FunctionTool:
    """Build the sequence-domain agent as a callable SDK tool."""
    specialist = Agent(
        name=NAME,
        instructions=INSTRUCTIONS,
        model=model,
        tools=[tool for tool in FUNCTION_TOOLS if tool.name in TOOL_NAMES],
        input_guardrails=[INPUT_GUARDRAIL],
        output_guardrails=[OUTPUT_GUARDRAIL],
    )
    return specialist.as_tool(tool_name=NAME, tool_description=DESCRIPTION, max_turns=4)
