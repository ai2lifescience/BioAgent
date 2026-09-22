"""Inspect a workspace file without performing domain analysis."""
from __future__ import annotations

from typing import Any, Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


import csv
from pathlib import Path
from typing import Literal
from tools.infrastructure.workspace import select_workspace_file
from tools.infrastructure.tool_support.artifacts import output

class InspectionResult(FunctionContract):
    path: str
    bytes: int
    line_count: int
    suffix: str
    preview: list[str]
    file_type: Literal["fasta", "table", "text"]
    record_count: int | None = None
    sequence_ids: list[str] = Field(default_factory=list)
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)


def inspect_bio_file(path: str, max_preview_lines: int = 20) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if file_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("File exceeds the 32 MB inspection limit.")
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    suffix = file_path.suffix.lower()
    result: dict[str, Any] = {
        "path": str(file_path),
        "bytes": file_path.stat().st_size,
        "line_count": len(lines),
        "suffix": suffix,
        "preview": lines[:max_preview_lines],
    }

    if suffix in {".fasta", ".fa", ".fna", ".faa"} or text.lstrip().startswith(">"):
        records = _parse_fasta_text(text)
        result.update(
            {
                "file_type": "fasta",
                "record_count": len(records),
                "sequence_ids": [record["id"] for record in records[:50]],
            }
        )
    elif suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        rows = list(csv.DictReader(lines, delimiter=delimiter))
        result.update(
            {
                "file_type": "table",
                "row_count": len(rows),
                "columns": list(rows[0].keys()) if rows else [],
            }
        )
    else:
        result["file_type"] = "text"

    return result


def _parse_fasta_text(text: str) -> list[dict[str, str]]:
    """Parse only enough FASTA structure for metadata inspection."""
    records: list[dict[str, str]] = []
    record_id = "sequence_1"
    sequence: list[str] = []
    seen_header = False
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if clean.startswith(">"):
            if seen_header or sequence:
                records.append({"id": record_id, "sequence": "".join(sequence)})
            seen_header = True
            record_id = clean[1:].split(None, 1)[0] or f"sequence_{len(records) + 1}"
            sequence = []
        else:
            sequence.append("".join(clean.split()))
    if seen_header or sequence:
        records.append({"id": record_id, "sequence": "".join(sequence)})
    return records


def _operation(*, path, max_preview_lines=20, context):
    source, public = select_workspace_file(context, path)
    result = inspect_bio_file(str(source), max_preview_lines)
    result["path"] = public
    return output(result)


@bio_function_tool()
async def file_inspection(
    ctx: RunContextWrapper[AgentRunContext],
    path: Annotated[str, Field(description="Existing workspace-relative file path.")],
    max_preview_lines: Annotated[int, Field(ge=0, le=200)] = 20,
) -> FunctionResult[InspectionResult]:
    """Inspect file format, size, columns, IDs, and preview lines."""
    return await invoke(ctx.context, "file_inspection", _operation,
                              {"path": path, "max_preview_lines": max_preview_lines}, FunctionResult[InspectionResult])


__all__ = ["file_inspection"]
