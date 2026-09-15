"""Small optional specialist agents exposed through SDK agent-as-tool calls."""

from __future__ import annotations

from agents import Agent, FunctionTool, Model

from harness.guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL
from tools.function_tools import FUNCTION_TOOLS


SPECIALIST_GROUPS: tuple[tuple[str, str, str, set[str]], ...] = (
    (
        "sequence_specialist",
        "Coordinate a task needing at least two of sequence_analysis, genome_map, blast_search, and protein_structure_analysis, or an explicit request for this specialist. For a single sequence metric, map, similarity search, or structure analysis, choose that direct tool.",
        "Carry out the delegated sequence, genome-map, BLAST, or structure-analysis task using the smallest necessary set of registered tools. Follow dependencies: wait for a required input before starting the next operation. Return results, evidence, and artifact paths; report missing inputs or failures.",
        {"sequence_analysis", "genome_map", "blast_search", "protein_structure_analysis"},
    ),
    (
        "retrieval_specialist",
        "Coordinate a task combining at least two of ncbi_retrieval, database_lookup, and species_report, or an explicit request for this specialist. A single NCBI download, database query, or cited species report belongs to its direct tool.",
        "Carry out the delegated retrieval or research task using the registered NCBI, database, and report tools. Use source records for record requests and species_report for cited synthesis. Preserve citations and downloaded paths; report missing inputs or failures.",
        {"ncbi_retrieval", "database_lookup", "species_report"},
    ),
    (
        "pipeline_specialist",
        "Coordinate pipeline execution followed by collection or review of its outputs, or an explicit request for this specialist. Use pipeline_runner directly for a run alone and pipeline_results directly for existing results.",
        "Carry out the delegated pipeline task with pipeline_runner and pipeline_results. Run the requested pipeline only through the approval-controlled tool, then collect outputs only after execution succeeds. Never invent paths, bypass approval, or rerun merely to review existing outputs.",
        {"pipeline_runner", "pipeline_results"},
    ),
)


def build_specialist_tools(model: Model) -> list[FunctionTool]:
    """Build domain agents as tools while retaining one root Runner.

    The root agent may call these only for domain requests that benefit from a
    focused instruction set. Nested runs share application context and tracing;
    the root supplies the relevant conversation details in the tool input.
    Specialists do not automatically read the root SQLite conversation.
    """
    specialist_tools: list[FunctionTool] = []
    for name, description, instructions, workflow_names in SPECIALIST_GROUPS:
        specialist = Agent(
            name=name,
            instructions=instructions,
            model=model,
            tools=[tool for tool in FUNCTION_TOOLS if tool.name in workflow_names],
            input_guardrails=[INPUT_GUARDRAIL],
            output_guardrails=[OUTPUT_GUARDRAIL],
        )
        specialist_tools.append(
            specialist.as_tool(
                tool_name=name,
                tool_description=description,
                max_turns=4,
            )
        )
    return specialist_tools
