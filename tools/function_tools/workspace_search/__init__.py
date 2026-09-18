"""Search text and PDF content in the active session workspace."""

from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import BioRunContext
from tools.common.results import run_workflow
from tools.common.tooling import bio_function_tool

from .workflow import workspace_search as _workflow


@bio_function_tool()
async def workspace_search(
    ctx: RunContextWrapper[BioRunContext],
    query: Annotated[str, Field(min_length=2, max_length=500, description="Words or phrase to find in workspace documents.")],
    path: Annotated[str | None, Field(description="Optional workspace-relative file path or filename to search.")] = None,
    max_results: Annotated[int, Field(ge=1, le=50, description="Maximum matching excerpts to return.")] = 10,
) -> str:
    """Search uploaded text documents and PDFs in the active workspace.

    Use this for finding relevant passages across multiple uploaded files.
    Use document_read when a complete PDF page range is needed. Results include
    workspace paths, page numbers when available, and bounded excerpts.
    """
    return await run_workflow(
        ctx.context,
        "workspace_search",
        _workflow,
        {"query": query, "path": path, "max_results": max_results},
        category="workspace_search",
        with_progress=False,
    )


__all__ = ["workspace_search"]
