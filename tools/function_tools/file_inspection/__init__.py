"""Inspect a local file's format, size, columns, IDs, and preview lines.

Use for file metadata, previews, columns, and row or record counts. Do not use
for biological sequence calculations, similarity searches, or genome maps.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import file_inspection as _workflow
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.results import run_workflow
from tools.infrastructure.tool_support.decorators import bio_function_tool


@bio_function_tool()
async def file_inspection(
    ctx: RunContextWrapper[AgentRunContext],
    path: Annotated[str, Field(description='Existing local file path from the user or a tool artifact. Do not invent a path or supply a database ID.')],
    max_preview_lines: Annotated[int, Field(ge=0, le=200)] = 20,
) -> str:
    """Inspect a local file without performing domain analysis.

    Use for file size, format, columns, row or record counts, sequence IDs,
    and preview lines. Use sequence_analysis for GC content or ORFs,
    protein_structure_analysis for structure measurements, and
    pipeline_shell results for collecting completed pipeline outputs.
    """
    return await run_workflow(ctx.context, 'file_inspection', _workflow,
        {'path': path, 'max_preview_lines': max_preview_lines}, category='file_inspection',
        with_progress=False)
