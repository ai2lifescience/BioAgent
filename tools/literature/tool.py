"""Literature concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.literature.core import collect_pubmed_records


PUBMED_COLLECT_TOOL = ToolDefinition(
    name="pubmed_collect",
    description="Collect PubMed records for a species or organism research question.",
    handler=collect_pubmed_records,
    category="literature",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "species_name": {"type": "string"},
            "question": {"type": "string"},
            "max_records": {"type": "integer", "default": 6, "minimum": 1},
            "email": {"type": "string"},
            "api_key": {"type": "string"},
        },
        "required": ["species_name", "question"],
    },
)
