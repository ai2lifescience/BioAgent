"""Bounded Biopython transformations and GenBank feature extraction."""

from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tooling.results import run_workflow
from tools.infrastructure.tooling.tooling import bio_function_tool

from .workflow import biology_analysis as _workflow


@bio_function_tool()
async def biology_analysis(
    ctx: RunContextWrapper[AgentRunContext],
    operation: Annotated[
        Literal["reverse_complement", "translate", "genbank_features"],
        Field(description="Biopython transformation or GenBank feature operation to run.")
    ],
    sequence: Annotated[str | None, Field(max_length=50000, description="Optional raw DNA or RNA sequence for transformation.")] = None,
    fasta_path: Annotated[str | None, Field(description="Optional uploaded FASTA workspace path for transformation.")] = None,
    genbank_path: Annotated[str | None, Field(description="Uploaded GenBank workspace path for genbank_features.")] = None,
    frame: Annotated[Literal[-3, -2, -1, 1, 2, 3], Field(description="Reading frame used by translate.")] = 1,
    max_records: Annotated[int, Field(ge=1, le=200, description="Maximum records to process.")] = 200,
) -> str:
    """Perform a bounded, deterministic Biopython transformation or feature read.

    Use sequence_analysis for length, GC, base or residue counts, FASTA
    summaries, and ORFs. Use this tool for reverse complements, translation,
    or GenBank feature extraction. It does not download files or create maps.
    """
    return await run_workflow(
        ctx.context,
        "biology_analysis",
        _workflow,
        {"operation": operation, "sequence": sequence, "fasta_path": fasta_path, "genbank_path": genbank_path, "frame": frame, "max_records": max_records},
        category="biology_analysis",
        with_progress=False,
    )


__all__ = ["biology_analysis"]
