"""Profile a bounded workspace table."""
from __future__ import annotations

import json
from typing import Annotated
import pandas as pd
from agents import RunContextWrapper
from pydantic import Field, JsonValue
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import input_path, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class TableProfile(FunctionContract):
    source_path: str
    rows: int
    columns: list[str]
    dtypes: dict[str, str]
    sample: list[dict[str, JsonValue]]
    missing_values: dict[str, int]
    missing_fraction: dict[str, float]
    missing_total: int
    metrics: list[dict[str, JsonValue]]
    truncated: bool


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


def _calculate(*, path: str, max_rows: int, context):
    frame, truncated = _read(context, path, max_rows)
    metrics = _json_rows(frame.describe(include="all").transpose().reset_index()) if len(frame.columns) else []
    return output({"source_path": path, "rows": len(frame), "columns": [str(v) for v in frame.columns], "dtypes": {str(k): str(v) for k, v in frame.dtypes.items()}, "sample": _json_rows(frame.head(5)), "missing_values": {str(k): int(v) for k, v in frame.isna().sum().items()}, "missing_fraction": {str(k): float(v) for k, v in frame.isna().mean().fillna(0).items()}, "missing_total": int(frame.isna().sum().sum()), "metrics": metrics, "truncated": truncated})


@bio_function_tool(timeout=120)
async def table_profile(ctx: RunContextWrapper[AgentRunContext], path: str, max_rows: Annotated[int, Field(ge=1, le=100_000)] = 100_000) -> FunctionResult[TableProfile]:
    """Profile a workspace-relative CSV, TSV, or Excel file."""
    return await invoke(ctx.context, "table_profile", _calculate, {"path": path, "max_rows": max_rows}, FunctionResult[TableProfile])


__all__ = ["table_profile", "TableProfile"]

