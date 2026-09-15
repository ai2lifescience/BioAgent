"""Inspect a local file's format, size, columns, IDs, and preview lines.

Use for file metadata and previews. Do not use for biological sequence
calculations, similarity searches, or genome maps.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import file_inspection as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def file_inspection(
    ctx: RunContextWrapper[BioRunContext],
    path: Annotated[str, Field(description='Existing local file path from the user or a tool artifact. Do not invent a path or supply a database ID.')],
    max_preview_lines: Annotated[int, Field(ge=0, le=200)] = 20,
) -> str:
    """Inspect a local FASTA, CSV, TSV, Markdown, or text file.

    Use for file size, format, columns, row or record counts, sequence IDs,
    and preview lines. Use sequence_analysis for GC content or ORFs,
    protein_structure_analysis for structure measurements, and
    pipeline_results for collecting completed pipeline outputs.
    """
    return await run_workflow(ctx.context, 'file_inspection', _workflow,
        {'path': path, 'max_preview_lines': max_preview_lines}, category='file_inspection',
        with_progress=False)
