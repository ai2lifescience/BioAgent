"""Calculate deterministic statistics for DNA, RNA, protein, or FASTA input.

Use for sequence length, GC content, base or residue counts, FASTA summaries,
and ORF detection. Do not use for sequence similarity, NCBI retrieval, file
metadata, or genome feature maps.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import sequence_analysis as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def sequence_analysis(
    ctx: RunContextWrapper[BioRunContext],
    sequence: Annotated[str | None, Field(description='Raw sequence or FASTA text to analyze. Use this, fasta_path, or a session artifact as the input source.')] = None,
    fasta_path: Annotated[str | None, Field(description='Existing local FASTA file to analyze when sequence text is not supplied.')] = None,
    artifact_ref: Annotated[Literal['latest_fasta'] | None, Field(description='Use latest_fasta to analyze the newest FASTA artifact in this session.')] = None,
    min_orf_length: Annotated[int, Field(description='Minimum ORF length to report.')] = 90,
) -> str:
    """Calculate deterministic biological sequence statistics.

    Use for DNA, RNA, or protein length, GC content, base or residue counts,
    FASTA summaries, and ORF detection. Accepts sequence text, a FASTA path,
    or the latest FASTA artifact. Use blast_search for similarity,
    file_inspection for file metadata or previews, and genome_map for a map.
    """
    return await run_workflow(ctx.context, 'sequence_analysis', _workflow,
        {'sequence': sequence, 'fasta_path': fasta_path, 'artifact_ref': artifact_ref, 'min_orf_length': min_orf_length}, category='sequence_analysis',
        with_progress=False)
