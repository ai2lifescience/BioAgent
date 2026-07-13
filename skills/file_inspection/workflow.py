"""File inspection skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "file_inspection",
        "description": (
            "Workflow for inspecting local FASTA, CSV, TSV, Markdown, or text "
            "files and summarizing counts, columns, sequence IDs, file size, "
            "and preview lines."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_preview_lines": {"type": "integer", "default": 20, "minimum": 0, "maximum": 200},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


def file_inspection(
    path: str,
    max_preview_lines: int = 20,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "file_inspection")
    result = context.run_tool(
        "file_inspect",
        {"path": path, "max_preview_lines": max_preview_lines}
    )["result"]
    answer = (
        "File inspection completed.\n"
        f"Path: {result.get('path')}\n"
        f"Type: {result.get('file_type')}\n"
        f"Lines: {result.get('line_count')}\n"
        f"Bytes: {result.get('bytes')}\n"
        f"Records/rows: {result.get('record_count', result.get('row_count', 'n/a'))}"
    )
    return {
        "skill": "file_inspection",
        "tool": "file_inspect",
        "answer": answer,
        "summary": (
            f"Inspected {result['file_type']} file with "
            f"{result.get('record_count', result.get('row_count', result['line_count']))} item(s)."
        ),
        **result,
    }
