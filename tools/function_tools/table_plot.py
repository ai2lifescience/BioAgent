"""Plot one numeric column from a bounded workspace table."""
from __future__ import annotations

from typing import Annotated
import pandas as pd
from agents import RunContextWrapper
from pydantic import Field
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, input_path, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class PlotResult(FunctionContract):
    source_path: str
    plot_path: str
    rows: int
    column: str
    truncated: bool


def _read(context, path, max_rows):
    source = input_path(context, path, (".csv", ".tsv", ".xlsx", ".xls"))
    if source.suffix.lower() in (".csv", ".tsv"):
        frame = pd.read_csv(source, sep="\t" if source.suffix.lower() == ".tsv" else ",", nrows=max_rows + 1)
    else:
        frame = pd.read_excel(source, nrows=max_rows + 1)
    if len(frame.columns) > 100:
        raise ValueError("Select a table with at most 100 columns.")
    return frame.iloc[:max_rows], len(frame) > max_rows


def _calculate(*, path: str, column: str | None, max_rows: int, context):
    frame, truncated = _read(context, path, max_rows)
    if column is None:
        numeric = frame.select_dtypes(include="number").columns
        if not len(numeric):
            raise ValueError("Table has no numeric columns to plot.")
        column = str(numeric[0])
    if column not in frame or not pd.api.types.is_numeric_dtype(frame[column]):
        raise ValueError("column must name an existing numeric column.")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    figure = Figure(figsize=(8, 4.5))
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    axis.hist(frame[column].dropna(), bins=30)
    axis.set(title=f"Distribution of {column}", xlabel=column)
    figure.tight_layout()
    target = destination(context, "distribution.png")
    figure.savefig(target, dpi=140)
    file = artifact(context, target)
    return output({"source_path": path, "plot_path": file["path"], "column": column, "rows": len(frame), "truncated": truncated}, file)


@bio_function_tool(timeout=120)
async def table_plot(ctx: RunContextWrapper[AgentRunContext], path: str, column: str | None = None, max_rows: Annotated[int, Field(ge=1, le=100_000)] = 100_000) -> FunctionResult[PlotResult]:
    """Plot one numeric table column as a histogram artifact."""
    return await invoke(ctx.context, "table_plot", _calculate, {"path": path, "column": column, "max_rows": max_rows}, FunctionResult[PlotResult])


__all__ = ["table_plot", "PlotResult"]

