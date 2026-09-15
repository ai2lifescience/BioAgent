"""Workflow for submitting a sequence to NCBI BLAST or polling an existing BLAST RID. Use only when the user explicitly asks for BLAST or sequence similarity search."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.blast_search import blast_search as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def blast_search(
    ctx: RunContextWrapper[BioRunContext],
    sequence: str | None = None,
    rid: Annotated[str | None, Field(description='Existing BLAST request ID to poll.')] = None,
    program: Literal['blastn', 'blastp', 'blastx', 'tblastn', 'tblastx'] = 'blastn',
    database: str = 'nt',
    hitlist_size: int = 10,
    expect: float = 10.0,
    wait: bool = False,
    timeout_seconds: int = 120,
) -> str:
    """Workflow for submitting a sequence to NCBI BLAST or polling an existing BLAST RID. Use only when the user explicitly asks for BLAST or sequence similarity search."""
    return await run_workflow(ctx.context, 'blast_search', _workflow,
        {'sequence': sequence, 'rid': rid, 'program': program, 'database': database, 'hitlist_size': hitlist_size, 'expect': expect, 'wait': wait, 'timeout_seconds': timeout_seconds}, category='bio_tool',
        with_progress=False)
