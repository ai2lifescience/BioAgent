"""Bounded, reproducible table analysis for uploaded workspace files."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from tools.common.context import WorkflowContext, ensure_workflow_context
from tools.workspace import select_workspace_file, workspace_output_path


SUPPORTED_SUFFIXES = (".csv", ".tsv", ".xlsx", ".xls")
MAX_ROWS = 100_000


def data_analysis(
    path: str | None = None,
    operation: str = "profile",
    column: str | None = None,
    group_by: list[str] | None = None,
    max_rows: int = 100_000,
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "data_analysis")
    operation = str(operation or "profile").strip().lower()
    if operation not in {"profile", "describe", "missing", "group", "plot"}:
        raise ValueError("operation must be one of profile, describe, missing, group, or plot.")
    limit = min(max(int(max_rows), 1), MAX_ROWS)
    source, display_path = select_workspace_file(context, path, suffixes=SUPPORTED_SUFFIXES)
    frame = _read_table(source, limit)
    result: dict[str, Any] = {
        "status": "ok",
        "operation": operation,
        "source_path": display_path,
        "rows": int(len(frame)),
        "columns": [str(value) for value in frame.columns],
        "truncated": bool(len(frame) >= limit),
    }
    if operation == "profile":
        result.update(_profile(frame))
    elif operation == "describe":
        result["metrics"] = _json_safe(frame.describe(include="all").transpose().reset_index().to_dict(orient="records"))
    elif operation == "missing":
        missing = frame.isna().sum().sort_values(ascending=False)
        result["missing_values"] = [{"column": str(name), "count": int(value), "fraction": round(float(value) / max(len(frame), 1), 6)} for name, value in missing.items()]
    elif operation == "group":
        result["groups"] = _group(frame, group_by, column)
    else:
        result.update(_plot(frame, column, context, display_path))
    result["summary"] = _summary(result, display_path)
    return result


def _read_table(source: Path, limit: int) -> pd.DataFrame:
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source, nrows=limit)
    if suffix == ".tsv":
        return pd.read_csv(source, sep="\t", nrows=limit)
    try:
        return pd.read_excel(source, nrows=limit)
    except ImportError as exc:
        raise ValueError("Excel analysis requires the optional openpyxl package; upload CSV or TSV instead.") from exc


def _profile(frame: pd.DataFrame) -> dict[str, Any]:
    dtypes = {str(name): str(dtype) for name, dtype in frame.dtypes.items()}
    sample = _json_safe(frame.head(5).to_dict(orient="records"))
    return {"dtypes": dtypes, "sample": sample, "missing_total": int(frame.isna().sum().sum())}


def _group(frame: pd.DataFrame, group_by: list[str] | None, column: str | None) -> list[dict[str, Any]]:
    keys = [str(value) for value in (group_by or []) if str(value).strip()]
    if not keys:
        raise ValueError("group operation requires at least one group_by column.")
    missing = [key for key in keys if key not in frame.columns]
    if missing:
        raise ValueError(f"Unknown group_by column(s): {', '.join(missing)}")
    grouped = frame.groupby(keys, dropna=False, sort=False)
    if column:
        if column not in frame.columns:
            raise ValueError(f"Unknown column: {column}")
        values = grouped[column].agg(["count", "mean", "median"]).reset_index()
    else:
        values = grouped.size().reset_index(name="count")
    return _json_safe(values.head(1000).to_dict(orient="records"))


def _plot(frame: pd.DataFrame, column: str | None, context: WorkflowContext, source: str) -> dict[str, Any]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    numeric = frame.select_dtypes(include="number").columns.tolist()
    selected = str(column or (numeric[0] if numeric else "")).strip()
    if not selected or selected not in frame.columns:
        raise ValueError("plot requires a numeric column, supplied with column.")
    if selected not in numeric:
        raise ValueError(f"Column {selected!r} is not numeric.")
    figure, axis = plt.subplots(figsize=(8, 4.5))
    frame[selected].dropna().plot(kind="hist", bins=30, ax=axis, title=f"Distribution of {selected}")
    axis.set_xlabel(selected)
    figure.tight_layout()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", selected).strip("._") or "column"
    destination = workspace_output_path(context, "analysis", f"{slug}_distribution.png")
    figure.savefig(destination, dpi=140)
    plt.close(figure)
    public = str(destination)
    if context.session_dir:
        try:
            public = destination.relative_to(Path(context.session_dir).resolve()).as_posix()
        except ValueError:
            pass
    return {"column": selected, "plot_path": public, "source": source}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if not isinstance(value, (str, bytes, list, dict, tuple)):
        try:
            missing = pd.isna(value)
            if isinstance(missing, bool) and missing:
                return None
            if hasattr(missing, "item") and bool(missing.item()):
                return None
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _summary(result: dict[str, Any], source: str) -> str:
    operation = result["operation"]
    if operation == "plot":
        return f"Created a distribution plot for {result['column']} from {source}."
    if operation == "group":
        return f"Grouped {result['rows']} row(s) from {source}."
    return f"Completed {operation} analysis for {result['rows']} row(s) and {len(result['columns'])} column(s) in {source}."


__all__ = ["data_analysis"]
