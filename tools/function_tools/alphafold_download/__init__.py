"""Download one AlphaFold Database prediction structure."""

from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tooling.results import run_workflow
from tools.infrastructure.tooling.tooling import bio_function_tool

from .workflow import alphafold_download as _workflow


@bio_function_tool()
async def alphafold_download(
    ctx: RunContextWrapper[AgentRunContext],
    accession: Annotated[str, Field(description="UniProt accession for the AlphaFold prediction, for example P0A7V8.")],
    file_format: Annotated[Literal["cif", "pdb"], Field(description="Structure format to save.")] = "cif",
) -> str:
    """Download an AlphaFold structure file for one UniProt accession.

    Use database_lookup for AlphaFold metadata and
    protein_structure_analysis for analyzing the resulting local structure.
    """
    return await run_workflow(
        ctx.context,
        "alphafold_download",
        _workflow,
        {"accession": accession, "file_format": file_format},
        category="alphafold",
        with_progress=False,
    )


__all__ = ["alphafold_download"]
