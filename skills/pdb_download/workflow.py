"""PDB structure download skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "pdb_download",
        "description": (
            "Workflow for downloading RCSB PDB structure files as mmCIF, PDB, "
            "or BinaryCIF. Use when the user asks to download, fetch, save, or "
            "retrieve a specific PDB structure file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pdb_id": {"type": "string", "description": "Four-character PDB ID, for example 1A3N."},
                "file_format": {
                    "type": "string",
                    "enum": ["cif", "pdb", "bcif"],
                    "default": "cif",
                    "description": "Structure file format to download.",
                },
                "output_dir": {"type": "string", "description": "Optional output directory."},
            },
            "required": ["pdb_id"],
            "additionalProperties": False,
        },
    },
}


def pdb_download(
    pdb_id: str,
    file_format: str = "cif",
    output_dir: str | None = None,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "pdb_download")
    resolved_output_dir = output_dir or context.artifact_path("structures")
    result = context.run_tool(
        "pdb_download",
        {
            "pdb_id": pdb_id,
            "file_format": file_format,
            "output_dir": resolved_output_dir,
        },
    )["result"]
    answer = (
        "PDB structure downloaded.\n"
        f"PDB ID: {result.get('pdb_id', pdb_id)}\n"
        f"Format: {result.get('file_format', file_format)}\n"
        f"Path: {result.get('structure_path')}\n"
        f"Source: {result.get('url')}"
    )
    return {
        "skill": "pdb_download",
        "tool": "pdb_download",
        "answer": answer,
        "summary": (
            f"Downloaded PDB {result.get('pdb_id', pdb_id)} "
            f"as {result.get('file_format', file_format)}."
        ),
        **result,
    }
