"""Read selectable text from a PDF in the active session workspace."""
from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from typing import Literal
from tools.infrastructure.workspace import select_workspace_file
from tools.infrastructure.workspace.pdf import read_pdf_text
from tools.infrastructure.tool_support.artifacts import output

class DocumentResult(FunctionContract):
    state: Literal["ok", "ocr_required"]
    source_path: str
    path: str | None = None
    page_count: int
    page_start: int | None = None
    page_end: int | None = None
    pages_read: int
    characters: int = 0
    text: str
    truncated: bool
    next_page_start: int | None = None
    next_char_offset: int | None = None


def _operation(*, path=None, page_start=1, page_end=None, char_offset=0, max_chars=40000, context):
    try:
        source, public = select_workspace_file(context, path, suffixes=(".pdf",))
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("No matching PDF is available in the active workspace.") from exc
    result = read_pdf_text(str(source), public, page_start, page_end, char_offset, max_chars)
    result["state"] = result.pop("status")
    result["source_path"] = public
    return output(result)


@bio_function_tool()
async def document_read(
    ctx: RunContextWrapper[AgentRunContext],
    path: Annotated[str | None, Field(description="Workspace-relative PDF path. Omit to use the newest uploaded PDF.")] = None,
    page_start: Annotated[int, Field(ge=1, le=100000)] = 1,
    page_end: Annotated[int | None, Field(ge=1, le=100000)] = None,
    char_offset: Annotated[int, Field(ge=0, le=10000000)] = 0,
    max_chars: Annotated[int, Field(ge=2000, le=120000)] = 40000,
) -> FunctionResult[DocumentResult]:
    """Read selectable PDF text with page markers and bounded continuation."""
    return await invoke(ctx.context, "document_read", _operation,
                              {"path": path, "page_start": page_start, "page_end": page_end,
                               "char_offset": char_offset, "max_chars": max_chars}, FunctionResult[DocumentResult])


__all__ = ["document_read"]
