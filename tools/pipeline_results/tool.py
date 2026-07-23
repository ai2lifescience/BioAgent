"""Tool definition for collecting completed pipeline results."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.pipeline_results.core import collect_pipeline_results


PIPELINE_RESULTS_COLLECT_TOOL = ToolDefinition(
    name="pipeline_results_collect",
    description=(
        "Collect the latest completed pipeline outputs in the current session, "
        "create a ZIP bundle, and return metrics and table previews."
    ),
    handler=collect_pipeline_results,
    category="pipeline",
    risk_level="medium",
    input_schema={
        "type": "object",
        "properties": {
            "artifacts": {"type": "array"},
            "collection_dir": {"type": "string"},
            "pipeline_name": {"type": "string"},
            "max_table_rows": {"type": "integer", "default": 10},
        },
        "required": ["artifacts", "collection_dir"],
        "additionalProperties": False,
    },
)
