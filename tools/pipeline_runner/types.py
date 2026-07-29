"""Shared pipeline runner data structures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PipelineContext:
    """Resolved runtime state shared by concrete pipeline engines."""

    pipeline_name: str
    pipeline_dir: Path
    runner_config: dict[str, Any]
    runner_config_path: Path
    raw_config: dict[str, Any]
    raw_config_path: Path
    input_path: Path
    original_input_path: Path
    session_input_path: Path | None
    input_staged: bool
    artifact_dir: Path | None
    stage_input: bool
    config_overrides: dict[str, Any]
    input_overrides: dict[str, str]
    resolved_input_overrides: dict[str, Any]
    input_override_records: list[dict[str, Any]]
    run_dir: Path
    output_dir: Path
    label: str
    timeout: int | None


@dataclass(frozen=True)
class RuntimeConfigWrite:
    """Generated runtime config and metadata."""

    path: Path
    staged_config_paths: list[dict[str, Any]]
    applied_config_overrides: dict[str, Any]
    output_records: list[dict[str, Any]]
    config: dict[str, Any]
