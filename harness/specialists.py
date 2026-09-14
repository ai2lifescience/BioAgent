"""Small optional specialist agents exposed through SDK agent-as-tool calls."""

from __future__ import annotations

from agents import Agent, FunctionTool, Model

from .guardrails import INPUT_GUARDRAIL, OUTPUT_GUARDRAIL
from .tools import build_tools


SPECIALIST_GROUPS: tuple[tuple[str, str, set[str]], ...] = (
    (
        "sequence_specialist",
        "Handle sequence, genome-map, BLAST, and protein-structure analysis. Delegate to the registered workflow tool and report its evidence.",
        {"sequence_analysis", "genome_map", "blast_search", "protein_structure_analysis"},
    ),
    (
        "retrieval_specialist",
        "Handle NCBI, database, and species-report retrieval. Use registered workflow tools and preserve citations.",
        {"ncbi_retrieval", "database_lookup", "species_report"},
    ),
    (
        "pipeline_specialist",
        "Handle approved pipeline execution and pipeline-result collection. Never invent paths or bypass the registered tools.",
        {"pipeline_runner", "pipeline_results"},
    ),
)


def build_specialist_tools(model: Model) -> list[FunctionTool]:
    """Build domain agents as tools while retaining one root Runner.

    The root agent may call these only for domain requests that benefit from a
    focused instruction set. Their nested runs use the same SDK context,
    session, guardrails, and trace as the root run.
    """
    specialist_tools: list[FunctionTool] = []
    for name, instructions, workflow_names in SPECIALIST_GROUPS:
        specialist = Agent(
            name=name,
            instructions=instructions,
            model=model,
            tools=build_tools(workflow_names),
            input_guardrails=[INPUT_GUARDRAIL],
            output_guardrails=[OUTPUT_GUARDRAIL],
        )
        specialist_tools.append(
            specialist.as_tool(
                tool_name=name,
                tool_description=f"Delegate a focused {name.replace('_', ' ')} task.",
                max_turns=4,
            )
        )
    return specialist_tools
