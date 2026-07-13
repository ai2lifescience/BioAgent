"""File inspection helpers for biological outputs."""

from __future__ import annotations

import csv
from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any

from tools.sequence import parse_fasta_text


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


def _slugify(text: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower()).strip("-._")
    return (slug or "report")[:max_length].strip("-._") or "report"


def write_markdown_report(
    markdown: str,
    entity_name: str,
    output_dir: str = os.getenv("BIOAGENT_REPORT_DIR", "runtime/reports"),
    suffix: str = "knowledge",
) -> dict[str, Any]:
    if not markdown.strip():
        raise ValueError("markdown must not be empty.")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_path / f"{_slugify(entity_name)}_{_slugify(suffix)}_{timestamp}.md"
    report_path.write_text(markdown, encoding="utf-8")
    return {
        "status": "ok",
        "report_path": str(report_path),
        "output_dir": str(output_path),
        "bytes": report_path.stat().st_size,
    }
