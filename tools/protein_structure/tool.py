"""Protein structure analysis concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.protein_structure.core import analyze_protein_structure_file


PROTEIN_STRUCTURE_ANALYZE_TOOL = ToolDefinition(
    name="protein_structure_analyze",
    description="Analyze a local PDB/mmCIF protein structure file and return compact structure statistics.",
    handler=analyze_protein_structure_file,
    category="bio_tool",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "structure_path": {"type": "string"},
        },
        "required": ["structure_path"],
    },
)
