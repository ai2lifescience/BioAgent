"""Generic runner entrypoint for approved plug-and-play pipeline folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.pipeline_runner.config import (
    load_pipeline_config,
    load_runner_config,
    normalize_config_overrides,
)
from tools.pipeline_runner.inputs import (
    default_input_slot,
    normalize_input_overrides,
    pipeline_input_specs,
    resolve_input_overrides,
    stage_pipeline_input,
    validate_declared_inputs,
    validate_input_path,
)
from tools.pipeline_runner.outputs import default_pipeline_output_dir
from tools.pipeline_runner.paths import (
    resolve_optional_artifact_dir,
    resolve_pipeline_dir,
    resolve_pipeline_input_path,
    resolve_pipeline_name,
    resolve_pipeline_output_path,
    resolve_pipeline_run_dir,
    resolve_project_path,
    safe_label,
)
from tools.pipeline_runner.types import PipelineContext


def run_pipeline(
    pipeline_name: str | None = None,
    input_path: str | None = None,
    output_dir: str | None = None,
    label: str | None = None,
    cores: int | None = None,
    dry_run: bool = False,
    timeout: int | None = None,
    artifact_dir: str | None = None,
    run_id: str | None = None,
    stage_input: bool = False,
    input_overrides: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an approved pipeline folder using its configured engine."""
    context = prepare_pipeline_context(
        pipeline_name=pipeline_name,
        input_path=input_path,
        output_dir=output_dir,
        label=label,
        timeout=timeout,
        artifact_dir=artifact_dir,
        run_id=run_id,
        stage_input=stage_input,
        input_overrides=input_overrides,
        config_overrides=config_overrides,
    )
    engine = str(context.runner_config.get("engine") or "").strip().lower()
    if engine == "shell":
        from tools.pipeline_runner.shell import run_shell_pipeline

        if dry_run:
            raise ValueError("dry_run is only supported for Snakemake and WDL pipelines.")
        return run_shell_pipeline(context)
    if engine == "snakemake":
        from tools.pipeline_runner.snakemake import run_snakemake_pipeline

        return run_snakemake_pipeline(context, cores=cores, dry_run=dry_run)
    if engine == "wdl":
        from tools.pipeline_runner.wdl import run_wdl_pipeline

        return run_wdl_pipeline(context, dry_run=dry_run)
    raise ValueError(
        f"Unsupported pipeline engine '{engine or '<missing>'}' in {context.runner_config_path}. "
        "Supported engines: shell, snakemake, wdl."
    )


def prepare_pipeline_context(
    pipeline_name: str | None = None,
    input_path: str | None = None,
    output_dir: str | None = None,
    label: str | None = None,
    timeout: int | None = None,
    artifact_dir: str | None = None,
    run_id: str | None = None,
    stage_input: bool = False,
    input_overrides: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> PipelineContext:
    resolved_pipeline_name = resolve_pipeline_name(pipeline_name)
    pipeline_dir = resolve_pipeline_dir(resolved_pipeline_name)
    runner_config, runner_config_path = load_runner_config(pipeline_dir)
    raw_config, raw_config_path = load_pipeline_config(pipeline_dir, runner_config)

    input_specs = pipeline_input_specs(runner_config)
    clean_input_overrides = normalize_input_overrides(input_overrides)
    resolved_input_overrides, input_override_records = resolve_input_overrides(
        clean_input_overrides,
        input_specs,
    )
    default_slot = default_input_slot(input_specs)
    default_spec = input_specs.get(default_slot) or {}
    default_config_key = str(default_spec.get("config_key") or "input_path")
    if input_path:
        legacy_input = resolve_project_path(input_path)
        validate_input_path(legacy_input, default_spec)
        resolved_input_overrides[default_config_key] = legacy_input
        input_override_records.append(
            {
                "slot": default_slot,
                "config_key": default_config_key,
                "path": str(legacy_input),
                "source": "input_path",
            }
        )

    input_value = (
        resolved_input_overrides.get(default_config_key)
        or resolved_input_overrides.get("input_path")
        or runner_config.get("default_input_path")
        or raw_config.get(default_config_key)
        or raw_config.get("input_path")
    )
    if not input_value:
        raise ValueError(
            f"Pipeline {resolved_pipeline_name} requires request input_path or "
            f"top-level input_path in {raw_config_path}."
        )
    original_input = (
        input_value
        if isinstance(input_value, Path)
        else resolve_pipeline_input_path(str(input_value), pipeline_dir)
    )
    if not original_input.exists():
        raise FileNotFoundError(f"Input file not found: {original_input}")
    validate_declared_inputs(raw_config, input_specs, resolved_input_overrides, pipeline_dir)

    resolved_artifact_dir = resolve_optional_artifact_dir(artifact_dir)
    clean_config_overrides = normalize_config_overrides(config_overrides)

    staged_input = stage_pipeline_input(original_input, resolved_artifact_dir) if stage_input else None
    resolved_input = staged_input or original_input
    if default_config_key in resolved_input_overrides:
        resolved_input_overrides[default_config_key] = resolved_input
    elif "input_path" in resolved_input_overrides:
        resolved_input_overrides["input_path"] = resolved_input

    resolved_run_dir = resolve_pipeline_run_dir(
        artifact_dir=resolved_artifact_dir,
        pipeline_name=resolved_pipeline_name,
        run_id=run_id,
    )
    output_value = output_dir or default_pipeline_output_dir(runner_config, raw_config)
    resolved_output = resolve_pipeline_output_path(output_value, resolved_run_dir)
    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    resolved_output.mkdir(parents=True, exist_ok=True)

    return PipelineContext(
        pipeline_name=resolved_pipeline_name,
        pipeline_dir=pipeline_dir,
        runner_config=runner_config,
        runner_config_path=runner_config_path,
        raw_config=raw_config,
        raw_config_path=raw_config_path,
        input_path=resolved_input,
        original_input_path=original_input,
        session_input_path=staged_input,
        input_staged=staged_input is not None and staged_input != original_input,
        artifact_dir=resolved_artifact_dir,
        stage_input=stage_input,
        config_overrides=clean_config_overrides,
        input_overrides=clean_input_overrides,
        resolved_input_overrides=resolved_input_overrides,
        input_override_records=input_override_records,
        run_dir=resolved_run_dir,
        output_dir=resolved_output,
        label=safe_label(
            label,
            str(raw_config.get("label") or runner_config.get("label") or resolved_pipeline_name),
        ),
        timeout=int(timeout or runner_config.get("timeout") or raw_config.get("timeout") or 300),
    )
