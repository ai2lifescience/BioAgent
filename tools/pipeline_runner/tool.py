"""Concrete runner tool definition for approved pipeline folders."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.pipeline_runner.core import run_pipeline


PIPELINE_RUNNER_TOOL = ToolDefinition(
    name="pipeline_runner",
    description=(
        "Run an approved pipeline folder under pipelines/. The folder must "
        "contain runner.yaml with engine: shell, engine: snakemake, or "
        "engine: wdl and a configured base input/config file with pipeline defaults."
    ),
    handler=run_pipeline,
    category="pipeline",
    risk_level="medium",
    input_schema={
        "type": "object",
        "properties": {
            "pipeline_name": {"type": "string", "default": "generic_shell"},
            "input_path": {"type": "string"},
            "output_dir": {
                "type": "string",
                "description": "Optional pipeline output directory. Relative paths resolve under the per-run directory.",
            },
            "label": {"type": "string"},
            "cores": {"type": "integer", "default": 1},
            "dry_run": {
                "type": "boolean",
                "description": "Run Snakemake in dry-run mode or validate WDL locally with miniwdl check.",
                "default": False,
            },
            "timeout": {"type": "integer", "default": 300},
            "input_overrides": {
                "type": "object",
                "description": "Map runner.yaml input slot names to runtime file paths.",
            },
            "config_overrides": {
                "type": "object",
                "description": "Pipeline-specific parameter overrides for keys under the base config params.",
            },
            "artifact_dir": {"type": "string"},
            "run_id": {"type": "string"},
        },
    },
)
