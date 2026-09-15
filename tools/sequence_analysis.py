"""Workflow for deterministic DNA, RNA, protein, or FASTA sequence analysis. Use for GC content, sequence length, base or residue counts, FASTA summaries, and ORF detection."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.sequence_analysis import sequence_analysis as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def sequence_analysis(
    ctx: RunContextWrapper[BioRunContext],
    sequence: Annotated[str | None, Field(description='Raw sequence or FASTA text.')] = None,
    fasta_path: Annotated[str | None, Field(description='Local FASTA file path.')] = None,
    artifact_ref: Annotated[Literal['latest_fasta'] | None, Field(description='Use latest_fasta to analyze the newest FASTA artifact in this session.')] = None,
    min_orf_length: Annotated[int, Field(description='Minimum ORF length.')] = 90,
) -> str:
    """Workflow for deterministic DNA, RNA, protein, or FASTA sequence analysis. Use for GC content, sequence length, base or residue counts, FASTA summaries, and ORF detection."""
    return await run_workflow(ctx.context, 'sequence_analysis', _workflow,
        {'sequence': sequence, 'fasta_path': fasta_path, 'artifact_ref': artifact_ref, 'min_orf_length': min_orf_length}, category='bio_tool',
        with_progress=False)
