"""Analyze a PDB or mmCIF structure from a local file, session artifact, or PDB ID.

Use for atoms, chains, residues, ligands, water, models, experimental method,
and resolution. Use ``pdb_download`` when the user wants to obtain a file.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import protein_structure_analysis as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def protein_structure_analysis(
    ctx: RunContextWrapper[BioRunContext],
    structure_path: Annotated[str | None, Field(description='Local .cif, .mmcif, or .pdb path.')] = None,
    pdb_id: Annotated[str | None, Field(description='Four-character PDB ID to download and then analyze when no local structure_path is supplied. Use pdb_download for download-only requests.')] = None,
    file_format: Annotated[Literal['cif', 'pdb'], Field(description='Text structure format to download when pdb_id is provided.')] = 'cif',
    artifact_ref: Annotated[Literal['latest_structure'] | None, Field(description='Use latest_structure to analyze the newest structure artifact in this session.')] = None,
) -> str:
    """Analyze a PDB or mmCIF structure from a file, session artifact, or PDB ID.

    Use for atom, chain, residue, ligand, water, and model counts, experimental
    method, and resolution. A PDB ID is downloaded before analysis. Use
    pdb_download when the user only wants the file and database_lookup for
    remote PDB metadata without local structure analysis.
    """
    return await run_workflow(ctx.context, 'protein_structure_analysis', _workflow,
        {'structure_path': structure_path, 'pdb_id': pdb_id, 'file_format': file_format, 'artifact_ref': artifact_ref}, category='protein_structure_analysis',
        with_progress=False)
