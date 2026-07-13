"""NCBI concrete tool definitions."""

from __future__ import annotations

from bio_data.ncbi_entrez import fetch_ncbi
from tools.base import ToolDefinition


NCBI_FETCH_TOOL = ToolDefinition(
    name="ncbi_fetch",
    description="Search NCBI Entrez and download FASTA plus metadata CSV records.",
    handler=fetch_ncbi,
    category="bio_data",
    risk_level="low",
    requires_confirmation=False,
    input_schema={
        "type": "object",
        "properties": {
            "term": {"type": "string"},
            "terms": {"type": "array", "items": {"type": "string"}},
            "genes": {"type": "array", "items": {"type": "string"}},
            "accessions": {"type": "array", "items": {"type": "string"}},
            "db": {"type": "string", "default": "nucleotide"},
            "max_records": {"type": "integer", "default": 10},
            "year": {"type": "integer"},
            "year_start": {"type": "integer"},
            "year_end": {"type": "integer"},
            "date_field": {"type": "string", "default": "PDAT"},
            "output_dir": {"type": "string"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "fasta_paths": {"type": "array", "items": {"type": "string"}},
            "metadata_paths": {"type": "array", "items": {"type": "string"}},
        },
    },
)
