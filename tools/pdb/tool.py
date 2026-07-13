"""PDB concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.pdb.core import download_pdb_structure_tool


PDB_DOWNLOAD_TOOL = ToolDefinition(
    name="pdb_download",
    description="Download an RCSB PDB structure file as mmCIF, PDB, or BinaryCIF.",
    handler=download_pdb_structure_tool,
    category="bio_api",
    risk_level="medium",
    input_schema={
        "type": "object",
        "properties": {
            "pdb_id": {"type": "string"},
            "file_format": {"type": "string", "enum": ["cif", "pdb", "bcif"], "default": "cif"},
            "output_dir": {"type": "string", "default": "runtime/pdb"},
        },
        "required": ["pdb_id"],
    },
)
