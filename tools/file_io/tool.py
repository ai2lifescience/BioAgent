"""File I/O concrete tool definitions."""

from __future__ import annotations

import os

from tools.base import ToolDefinition
from tools.file_io.core import inspect_bio_file, write_markdown_report


FILE_INSPECT_TOOL = ToolDefinition(
    name="file_inspect",
    description="Inspect local FASTA, CSV, TSV, Markdown, or text files.",
    handler=inspect_bio_file,
    category="file_io",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_preview_lines": {"type": "integer", "default": 20},
        },
        "required": ["path"],
    },
)

MARKDOWN_REPORT_WRITER_TOOL = ToolDefinition(
    name="markdown_report_writer",
    description="Write a Markdown report to a timestamped local file.",
    handler=write_markdown_report,
    category="file_io",
    risk_level="medium",
    input_schema={
        "type": "object",
        "properties": {
            "markdown": {"type": "string"},
            "entity_name": {"type": "string"},
            "output_dir": {
                "type": "string",
                "default": os.getenv("BIOAGENT_REPORT_DIR", "runtime/reports"),
            },
            "suffix": {"type": "string", "default": "knowledge"},
        },
        "required": ["markdown", "entity_name"],
    },
)
