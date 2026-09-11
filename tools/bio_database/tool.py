"""Biological database concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.bio_database.core import search_bio_database_tool


DATABASE_NAMES = ["uniprot", "interpro", "kegg", "quickgo", "pdb", "alphafold"]


BIO_DATABASE_SEARCH_TOOL = ToolDefinition(
    name="bio_database_search",
    description=(
        "Query UniProt, InterPro, KEGG, QuickGO, PDB, or AlphaFold DB and return "
        "normalized biological records."
    ),
    handler=search_bio_database_tool,
    category="bio_api",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "database": {"type": "string", "enum": DATABASE_NAMES},
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
            "operation": {"type": "string"},
            "taxid": {"type": "integer", "minimum": 1},
            "download": {"type": "boolean", "default": False},
            "file_format": {"type": "string", "enum": ["cif", "pdb"], "default": "cif"},
            "output_dir": {"type": "string"},
        },
        "required": ["database", "query"],
        "additionalProperties": False,
    },
)
