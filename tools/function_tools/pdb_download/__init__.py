"""Download one specific structure file from RCSB PDB.

Use when the user asks to fetch, save, or download a PDB structure. Do not use
to analyze an existing structure; use ``protein_structure_analysis`` instead.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import pdb_download as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def pdb_download(
    ctx: RunContextWrapper[BioRunContext],
    pdb_id: Annotated[str, Field(description='Four-character PDB ID, for example 1A3N.')],
    file_format: Annotated[Literal['cif', 'pdb', 'bcif'], Field(description='Structure file format to download.')] = 'cif',
    output_dir: Annotated[str | None, Field(description='Optional output directory.')] = None,
) -> str:
    """Download one RCSB PDB structure file in the requested format.

    Use for fetch, save, or download requests for a specific PDB ID in mmCIF,
    PDB, or BinaryCIF format. Writes a local structure file. Use
    database_lookup for remote PDB metadata or search and
    protein_structure_analysis when the goal is analyzing a structure.
    """
    return await run_workflow(ctx.context, 'pdb_download', _workflow,
        {'pdb_id': pdb_id, 'file_format': file_format, 'output_dir': output_dir}, category='pdb',
        with_progress=False)
