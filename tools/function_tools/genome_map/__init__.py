"""Create a genome feature map from GenBank, GFF plus FASTA, or FASTA.

Use for gene layout, feature layout, circular maps, linear maps, and ORF
maps. Do not use for sequence statistics or file-only inspection.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import genome_map as _workflow
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.results import run_workflow
from tools.infrastructure.tool_support.decorators import bio_function_tool


@bio_function_tool()
async def genome_map(
    ctx: RunContextWrapper[AgentRunContext],
    fasta_path: Annotated[str | None, Field(description='Local FASTA file path.')] = None,
    genbank_path: Annotated[str | None, Field(description='Local GenBank .gb/.gbk file path.')] = None,
    gff_path: Annotated[str | None, Field(description='Optional local GFF/GFF3 annotation path.')] = None,
    artifact_ref: Annotated[Literal['latest_fasta'] | None, Field(description='Use latest_fasta to map the newest FASTA artifact in this session.')] = None,
    layout: Literal['circular', 'linear'] = 'circular',
    label: Annotated[str | None, Field(description='Optional map label.')] = None,
    min_orf_length: int = 90,
) -> str:
    """Create a genome feature map from biological sequence files.

    Use when the user asks for a circular or linear map of genome features,
    genes, or ORFs. Accepts GenBank, GFF plus FASTA, or FASTA and writes map
    artifacts. Use sequence_analysis for sequence metrics and species_report
    for a cited explanation of genome structure without a map request.
    """
    return await run_workflow(ctx.context, 'genome_map', _workflow,
        {'fasta_path': fasta_path, 'genbank_path': genbank_path, 'gff_path': gff_path, 'artifact_ref': artifact_ref, 'layout': layout, 'label': label, 'min_orf_length': min_orf_length}, category='genome_map',
        with_progress=False)
