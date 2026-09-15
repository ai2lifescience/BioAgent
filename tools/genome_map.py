"""Create a genome feature map from GenBank, GFF+FASTA, or FASTA. Use for genome structure, genome map, gene layout, feature layout, circular genome maps, linear genome maps, and ORF maps."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.genome_map import genome_map as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


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
    """Create a genome feature map from GenBank, GFF+FASTA, or FASTA. Use for genome structure, genome map, gene layout, feature layout, circular genome maps, linear genome maps, and ORF maps."""
    return await run_workflow(ctx.context, 'genome_map', _workflow,
        {'fasta_path': fasta_path, 'genbank_path': genbank_path, 'gff_path': gff_path, 'artifact_ref': artifact_ref, 'layout': layout, 'label': label, 'min_orf_length': min_orf_length}, category='bio_tool',
        with_progress=False)
