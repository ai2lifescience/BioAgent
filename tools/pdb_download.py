"""Workflow for downloading RCSB PDB structure files as mmCIF, PDB, or BinaryCIF. Use when the user asks to download, fetch, save, or retrieve a specific PDB structure file."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.pdb_download import pdb_download as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def pdb_download(
    ctx: RunContextWrapper[BioRunContext],
    pdb_id: Annotated[str, Field(description='Four-character PDB ID, for example 1A3N.')],
    file_format: Annotated[Literal['cif', 'pdb', 'bcif'], Field(description='Structure file format to download.')] = 'cif',
    output_dir: Annotated[str | None, Field(description='Optional output directory.')] = None,
) -> str:
    """Workflow for downloading RCSB PDB structure files as mmCIF, PDB, or BinaryCIF. Use when the user asks to download, fetch, save, or retrieve a specific PDB structure file."""
    return await run_workflow(ctx.context, 'pdb_download', _workflow,
        {'pdb_id': pdb_id, 'file_format': file_format, 'output_dir': output_dir}, category='bio_api',
        with_progress=False)
