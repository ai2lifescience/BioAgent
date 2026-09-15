"""Workflow for deterministic analysis of local PDB, mmCIF, or downloaded structure files. Use for atom counts, chains, residues, ligands, water, models, experimental method, and resolution."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.protein_structure_analysis import protein_structure_analysis as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def protein_structure_analysis(
    ctx: RunContextWrapper[BioRunContext],
    structure_path: Annotated[str | None, Field(description='Local .cif, .mmcif, or .pdb path.')] = None,
    pdb_id: Annotated[str | None, Field(description='Four-character PDB ID. The skill downloads mmCIF first, then analyzes it.')] = None,
    file_format: Annotated[Literal['cif', 'pdb'], Field(description='Text structure format to download when pdb_id is provided.')] = 'cif',
    artifact_ref: Annotated[Literal['latest_structure'] | None, Field(description='Use latest_structure to analyze the newest structure artifact in this session.')] = None,
) -> str:
    """Workflow for deterministic analysis of local PDB, mmCIF, or downloaded structure files. Use for atom counts, chains, residues, ligands, water, models, experimental method, and resolution."""
    return await run_workflow(ctx.context, 'protein_structure_analysis', _workflow,
        {'structure_path': structure_path, 'pdb_id': pdb_id, 'file_format': file_format, 'artifact_ref': artifact_ref}, category='bio_tool',
        with_progress=False)
