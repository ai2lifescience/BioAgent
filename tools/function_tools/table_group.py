"""Aggregate a bounded workspace table by one or more columns."""
from __future__ import annotations

import json
from typing import Annotated
import pandas as pd
from agents import RunContextWrapper
from pydantic import Field, JsonValue
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, input_path, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class TableGroups(FunctionContract):
    source_path: str
    rows: int
    groups: list[dict[str, JsonValue]]
    total: int
    returned: int
    input_truncated: bool
    truncated: bool
    table_path: str


def _json_rows(frame):
    rows = json.loads(frame.to_json(orient="records", date_format="iso"))
    for row in rows:
        for key, value in row.items():
            if isinstance(value, str) and len(value) > 2000:
                row[key] = value[:2000] + "…"
    return rows


def _read(context, path, max_rows):
    source = input_path(context, path, (".csv", ".tsv", ".xlsx", ".xls"))
    if source.suffix.lower() in (".csv", ".tsv"):
        frame = pd.read_csv(source, sep="\t" if source.suffix.lower() == ".tsv" else ",", nrows=max_rows + 1)
    else:
        frame = pd.read_excel(source, nrows=max_rows + 1)
    if len(frame.columns) > 100:
        raise ValueError("Select a table with at most 100 columns.")
    return frame.iloc[:max_rows], len(frame) > max_rows


def _calculate(*, path: str, group_by: list[str], column: str | None, max_rows: int, context):
    frame, input_truncated = _read(context, path, max_rows)
    if len(set(group_by)) != len(group_by) or any(key not in frame for key in group_by):
        raise ValueError("group_by must contain unique existing column names.")
    grouped = frame.groupby(group_by, dropna=False, sort=False)
    if column:
        if column in group_by or column not in frame or not pd.api.types.is_numeric_dtype(frame[column]):
            raise ValueError("column must name a numeric column outside group_by.")
        values = grouped[column].agg(["count", "mean", "median"]).reset_index()
    else:
        values = grouped.size().reset_index(name="count")
    target = destination(context, "groups.csv")
    values.to_csv(target, index=False)
    file = artifact(context, target)
    preview = _json_rows(values.head(100))
    return output({"source_path": path, "rows": len(frame), "groups": preview, "total": len(values), "returned": len(preview), "input_truncated": input_truncated, "truncated": input_truncated or len(values) > len(preview), "table_path": file["path"]}, file)


@bio_function_tool(timeout=120)
async def table_group(ctx: RunContextWrapper[AgentRunContext], path: str, group_by: Annotated[list[str], Field(min_length=1, max_length=10)], column: str | None = None, max_rows: Annotated[int, Field(ge=1, le=100_000)] = 100_000) -> FunctionResult[TableGroups]:
    """Aggregate rows by existing columns and save all groups as CSV."""
    return await invoke(ctx.context, "table_group", _calculate, {"path": path, "group_by": group_by, "column": column, "max_rows": max_rows}, FunctionResult[TableGroups])


__all__ = ["table_group", "TableGroups"]

