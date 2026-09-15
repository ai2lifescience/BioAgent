"""Submit a sequence to NCBI BLAST or poll an existing BLAST request.

Use only for sequence similarity, homology, or BLAST requests. Do not use for
GC content, ORFs, general sequence statistics, NCBI record retrieval, or
genome maps.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import blast_search as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def blast_search(
    ctx: RunContextWrapper[BioRunContext],
    sequence: Annotated[str | None, Field(description='Sequence or FASTA text to submit for similarity search. Provide rid instead to poll an existing request.')] = None,
    rid: Annotated[str | None, Field(description='Existing BLAST request ID to poll.')] = None,
    program: Literal['blastn', 'blastp', 'blastx', 'tblastn', 'tblastx'] = 'blastn',
    database: str = 'nt',
    hitlist_size: int = 10,
    expect: float = 10.0,
    wait: bool = False,
    timeout_seconds: int = 120,
) -> str:
    """Submit a sequence to NCBI BLAST or poll an existing BLAST request.

    Use when the user requests BLAST, sequence similarity, or finding related
    sequences. A request ID polls an existing search. Use sequence_analysis
    for GC content or other local statistics and ncbi_retrieval for known
    records. Submitting a new search sends the sequence to NCBI.
    """
    return await run_workflow(ctx.context, 'blast_search', _workflow,
        {'sequence': sequence, 'rid': rid, 'program': program, 'database': database, 'hitlist_size': hitlist_size, 'expect': expect, 'wait': wait, 'timeout_seconds': timeout_seconds}, category='blast_search',
        with_progress=False)
