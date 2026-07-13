"""Sequence concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.sequence.core import analyze_sequence_text


SEQUENCE_ANALYZE_TOOL = ToolDefinition(
    name="sequence_analyze",
    description="Analyze sequence length, type, GC content, residue counts, and ORFs.",
    handler=analyze_sequence_text,
    category="bio_tool",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "sequence": {"type": "string"},
            "fasta_path": {"type": "string"},
            "min_orf_length": {"type": "integer", "default": 90},
        },
    },
)
