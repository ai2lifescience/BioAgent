"""Analyze a PDB or mmCIF structure from a local file or session artifact.

Use for atoms, chains, residues, ligands, water, models, experimental method,
and resolution. Use ``pdb_download`` first when the user provides a PDB ID.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import protein_structure_analysis as _workflow
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.results import run_workflow
from tools.infrastructure.tool_support.decorators import bio_function_tool


@bio_function_tool()
async def protein_structure_analysis(
    ctx: RunContextWrapper[AgentRunContext],
    structure_path: Annotated[str | None, Field(description='Local .cif, .mmcif, or .pdb path.')] = None,
    artifact_ref: Annotated[Literal['latest_structure'] | None, Field(description='Use latest_structure to analyze the newest structure artifact in this session.')] = None,
) -> str:
    """Analyze an existing PDB or mmCIF structure from a file or artifact.

    Use for atom, chain, residue, ligand, water, and model counts, experimental
    method, and resolution. Use pdb_download before this tool for a remote PDB
    ID, and use database_lookup for remote PDB metadata without local analysis.
    """
    return await run_workflow(ctx.context, 'protein_structure_analysis', _workflow,
        {'structure_path': structure_path, 'artifact_ref': artifact_ref}, category='protein_structure_analysis',
        with_progress=False)
