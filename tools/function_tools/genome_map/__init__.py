"""Create a genome feature map from GenBank, GFF plus FASTA, or FASTA.

Use for gene layout, feature layout, circular maps, linear maps, and ORF
maps. Do not use for sequence statistics or file-only inspection.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import genome_map as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def genome_map(
    ctx: RunContextWrapper[BioRunContext],
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
