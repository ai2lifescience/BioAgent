"""Markdown report writer owned by the species_report function tool."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any

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
