"""Biological database concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.bio_database.core import search_bio_database_tool


BIO_DATABASE_SEARCH_TOOL = ToolDefinition(
    name="bio_database_search",
    description="Search UniProt or PDB and return normalized biological records.",
    handler=search_bio_database_tool,
    category="bio_api",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "database": {"type": "string", "enum": ["uniprot", "pdb"]},
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["database", "query"],
    },
)
