"""Reporting concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.reporting.core import (
    collect_species_model_opinions,
    synthesize_species_markdown_report,
)


SPECIES_MODEL_OPINIONS_TOOL = ToolDefinition(
    name="species_model_opinions",
    description="Collect direct model opinions for a species or organism question.",
    handler=collect_species_model_opinions,
    category="reporting",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "species_name": {"type": "string"},
            "question": {"type": "string"},
            "model_keys": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["species_name", "question"],
    },
)

SPECIES_REPORT_SYNTHESIS_TOOL = ToolDefinition(
    name="species_report_synthesis",
    description="Synthesize a Markdown species report from retrieved evidence and model opinions.",
    handler=synthesize_species_markdown_report,
    category="reporting",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "species_name": {"type": "string"},
            "question": {"type": "string"},
            "retrieval_context": {"type": "string"},
            "model_answers": {"type": "object"},
            "sources": {"type": "array", "items": {"type": "object"}},
            "model_key": {"type": "string"},
        },
        "required": ["species_name", "question", "model_answers", "sources"],
    },
)
