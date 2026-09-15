"""File inspection helpers for biological outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from tools.function_tools.sequence_analysis.analysis import parse_fasta_text


def inspect_bio_file(path: str, max_preview_lines: int = 20) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {path}")

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
        records = parse_fasta_text(text)
        result.update(
            {
                "file_type": "fasta",
                "record_count": len(records),
                "sequence_ids": [record["id"] for record in records[:50]],
                "total_sequence_length": sum(len(record["sequence"]) for record in records),
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

