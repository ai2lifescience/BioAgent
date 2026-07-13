"""Genome map concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.genome_map.core import create_genome_map


GENOME_MAP_TOOL = ToolDefinition(
    name="genome_map",
    description="Create a linear or circular SVG genome feature map from GenBank, GFF+FASTA, or FASTA ORFs.",
    handler=create_genome_map,
    category="bio_tool",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "fasta_path": {"type": "string"},
            "genbank_path": {"type": "string"},
            "gff_path": {"type": "string"},
            "output_dir": {"type": "string"},
            "label": {"type": "string"},
            "layout": {"type": "string", "enum": ["circular", "linear"], "default": "circular"},
            "min_orf_length": {"type": "integer", "default": 90},
        },
        "anyOf": [
            {"required": ["fasta_path"]},
            {"required": ["genbank_path"]},
        ],
    },
)
