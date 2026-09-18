"""Bounded statistics and plots for tabular workspace files."""

from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.common.results import run_workflow
from tools.common.tooling import bio_function_tool

from .workflow import data_analysis as _workflow


@bio_function_tool()
async def data_analysis(
    ctx: RunContextWrapper[AgentRunContext],
    operation: Annotated[Literal["profile", "describe", "missing", "group", "plot"], Field(description="Bounded table operation to run.")],
    path: Annotated[str | None, Field(description="Optional uploaded CSV, TSV, or Excel workspace path.")] = None,
    column: Annotated[str | None, Field(description="Numeric or aggregate column for group or plot operations.")] = None,
    group_by: Annotated[list[str] | None, Field(description="Column names used by the group operation.")] = None,
    max_rows: Annotated[int, Field(ge=1, le=100000, description="Maximum rows read from the source file.")] = 100000,
) -> str:
    """Profile or summarize an uploaded table with bounded pandas operations.

    This tool does not execute user-supplied Python. Use code tools for an
    explicitly requested, reviewable programmatic analysis.
    """
    return await run_workflow(
        ctx.context,
        "data_analysis",
        _workflow,
        {"path": path, "operation": operation, "column": column, "group_by": group_by, "max_rows": max_rows},
        category="data_analysis",
        with_progress=False,
    )


__all__ = ["data_analysis"]
