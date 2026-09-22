"""Self-contained SDK capability: report_write."""
from __future__ import annotations

import re
from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import output, destination, artifact
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract as Contract, FunctionResult as Result


class ReportResult(Contract):
    report_path: str
    bytes: int


def _operation(*, markdown: str, title: str, context):
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", title).strip("._")[:60] or "report"
    target = destination(context, slug + ".md")
    target.write_text(markdown, encoding="utf-8")
    file = artifact(context, target)
    return output({"report_path": file["path"], "bytes": file["size"]}, file)


@bio_function_tool(timeout=120)
async def report_write(
    ctx: RunContextWrapper[AgentRunContext],
    markdown: Annotated[str, Field(min_length=1, max_length=200_000)],
    title: Annotated[str, Field(min_length=1, max_length=200)],
) -> Result[ReportResult]:
    """Save supplied Markdown in a unique workspace artifact. Performs no synthesis or retrieval."""
    return await invoke(ctx.context, "report_write", _operation, {"markdown": markdown, "title": title}, Result[ReportResult])


__all__ = ["report_write"]
