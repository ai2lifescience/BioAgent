"""Trusted web concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.web.core import collect_trusted_web_records


TRUSTED_WEB_COLLECT_TOOL = ToolDefinition(
    name="trusted_web_collect",
    description="Collect trusted authority web pages for a species or organism question.",
    handler=collect_trusted_web_records,
    category="web",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "species_name": {"type": "string"},
            "question": {"type": "string"},
            "max_pages": {"type": "integer", "default": 6, "minimum": 0},
        },
        "required": ["species_name", "question"],
    },
)
