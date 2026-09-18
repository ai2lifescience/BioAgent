"""Read selectable text from a PDF in the active session workspace."""

from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import BioRunContext
from tools.common.results import run_workflow
from tools.common.tooling import bio_function_tool

from .workflow import document_read as _workflow


@bio_function_tool()
async def document_read(
    ctx: RunContextWrapper[BioRunContext],
    path: Annotated[
        str | None,
        Field(
            description=(
                "Existing PDF path from the active session workspace. Use the "
                "workspace_path returned by workspace listing when known. Omit "
                "this value when the user refers to the latest uploaded PDF."
            )
        ),
    ] = None,
    page_start: Annotated[int, Field(ge=1, le=100000)] = 1,
    page_end: Annotated[int | None, Field(ge=1, le=100000)] = None,
    char_offset: Annotated[
        int,
        Field(
            ge=0,
            le=10000000,
            description="Character offset within page_start when continuing a truncated page.",
        ),
    ] = 0,
    max_chars: Annotated[
        int,
        Field(
            ge=2000,
            le=120000,
            description="Maximum extracted characters returned in this call.",
        ),
    ] = 40000,
) -> str:
    """Read selectable text from a session PDF for answering or summarizing it.

    Use this when the user asks to summarize, explain, review, or extract facts
    from a PDF that is already in the workspace. If the user says "my uploaded
    PDF" without giving a path, omit path and the newest uploaded PDF is used.
    Text is returned with page
    markers so the final answer can cite page numbers. For long documents, use
    page_start and page_end to read additional ranges; if the result is
    truncated, continue from its next_page_start and next_char_offset before
    summarizing the whole document. Scanned PDFs return an OCR-required result
    instead of fabricated text.
    """
    return await run_workflow(
        ctx.context,
        "document_read",
        _workflow,
        {
            "path": path,
            "page_start": page_start,
            "page_end": page_end,
            "char_offset": char_offset,
            "max_chars": max_chars,
        },
        category="document_read",
        with_progress=False,
    )


__all__ = ["document_read"]
