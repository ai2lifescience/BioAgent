"""Workflow for inspecting local FASTA, CSV, TSV, Markdown, or text files and summarizing counts, columns, sequence IDs, file size, and preview lines."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.file_inspection import file_inspection as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def file_inspection(
    ctx: RunContextWrapper[BioRunContext],
    path: str,
    max_preview_lines: Annotated[int, Field(ge=0, le=200)] = 20,
) -> str:
    """Workflow for inspecting local FASTA, CSV, TSV, Markdown, or text files and summarizing counts, columns, sequence IDs, file size, and preview lines."""
    return await run_workflow(ctx.context, 'file_inspection', _workflow,
        {'path': path, 'max_preview_lines': max_preview_lines}, category='file_io',
        with_progress=False)
