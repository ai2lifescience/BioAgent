"""BLAST concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.blast.core import run_blast_search


BLAST_SEARCH_TOOL = ToolDefinition(
    name="blast_search",
    description="Submit an NCBI BLAST URL API search or poll an existing BLAST RID.",
    handler=run_blast_search,
    category="bio_tool",
    risk_level="medium",
    requires_confirmation=False,
    input_schema={
        "type": "object",
        "properties": {
            "sequence": {"type": "string"},
            "rid": {"type": "string"},
            "program": {"type": "string", "default": "blastn"},
            "database": {"type": "string", "default": "nt"},
            "hitlist_size": {"type": "integer", "default": 10},
            "expect": {"type": "number", "default": 10.0},
            "wait": {"type": "boolean", "default": False},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
        "anyOf": [
            {"required": ["sequence"]},
            {"required": ["rid"]},
        ],
    },
)
