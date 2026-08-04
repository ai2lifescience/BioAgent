"""Pipeline runner config loading and runtime config writing."""

from __future__ import annotations

import copy
from pathlib import Path
import re
from typing import Any

from tools.pipeline_config import load_yaml_config, write_yaml_config
from tools.pipeline_runner.inputs import (
    rewrite_top_level_path_fields,
    stringify_input_value,
    staged_input_records,
)
from tools.pipeline_runner.outputs import rewrite_output_config_fields
from tools.pipeline_runner.paths import resolve_pipeline_file
from tools.pipeline_runner.types import PipelineContext, RuntimeConfigWrite


def load_pipeline_config(
    pipeline_dir: Path,
    runner_config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    config_file = None
    if runner_config:
        config_file = (
            runner_config.get("config")
            or runner_config.get("config_file")
            or runner_config.get("config_path")
            or runner_config.get("inputs_json")
            or runner_config.get("inputs_file")
        )
    config_path = resolve_pipeline_file(
        pipeline_dir,
        str(config_file) if config_file else None,
        fallback="config.yaml",
        label="Pipeline config",
    )
    return load_yaml_config(config_path), config_path


def load_runner_config(pipeline_dir: Path) -> tuple[dict[str, Any], Path]:
    config_path = pipeline_dir / "runner.yaml"
    return load_yaml_config(config_path), config_path


def write_runtime_config(
    context: PipelineContext,
    extra: dict[str, Any] | None = None,
) -> RuntimeConfigWrite:
    """Write the config file passed to the concrete pipeline engine."""
    runtime_config = copy.deepcopy(context.raw_config)
    input_records = apply_input_overrides(runtime_config, context)
    requested_overrides = apply_runner_preset(
        runtime_config,
        context.config_overrides,
        context.runner_config,
    )
    applied_config_overrides = apply_runner_param_overrides(
        runtime_config,
        requested_overrides,
        context.runner_config,
    )
    if applied_config_overrides is None:
        applied_config_overrides = apply_config_overrides(runtime_config, requested_overrides)
    output_records = rewrite_output_config_fields(runtime_config, context)
    output_config_keys = {str(record.get("config_key") or "") for record in output_records}
    path_records = rewrite_top_level_path_fields(runtime_config, context, skip_keys=output_config_keys)
    runtime_config.update(
        {
            "pipeline_name": context.pipeline_name,
            "input_path": str(context.input_path),
            "original_input_path": str(context.original_input_path),
            "session_input_path": str(context.session_input_path or ""),
            "input_staged": context.input_staged,
            "run_dir": str(context.run_dir),
            "output_dir": str(context.output_dir),
            "label": context.label,
            "timeout": context.timeout,
            "input_overrides": {
                key: stringify_input_value(path)
                for key, path in context.resolved_input_overrides.items()
            },
            **dict(extra or {}),
        }
    )

    runtime_config_path = context.run_dir / "config.runtime.yaml"
    write_yaml_config(runtime_config, runtime_config_path)
    return RuntimeConfigWrite(
        path=runtime_config_path,
        staged_config_paths=[*staged_input_records(context), *input_records, *path_records],
        applied_config_overrides=applied_config_overrides,
        output_records=output_records,
    )


def apply_input_overrides(
    runtime_config: dict[str, Any],
    context: PipelineContext,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for config_key, path in context.resolved_input_overrides.items():
        runtime_config[config_key] = stringify_input_value(path)
    for record in context.input_override_records:
        config_key = str(record.get("config_key") or "")
        if not config_key or config_key == "input_path":
            continue
        records.append(dict(record))
    return records


def apply_config_overrides(
    runtime_config: dict[str, Any],
    requested_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Apply request overrides to keys under the base config params."""
    if not requested_overrides:
        return {}

    params = runtime_config.get("params")
    if not isinstance(params, dict):
        raise ValueError("This pipeline does not define base config params.")

    unknown = sorted(set(requested_overrides) - set(params))
    if unknown:
        allowed = ", ".join(sorted(str(key) for key in params)) or "<none>"
        raise ValueError(
            f"Unsupported config override(s): {', '.join(unknown)}. "
            f"Allowed params for this pipeline: {allowed}."
        )

    applied: dict[str, Any] = {}
    for key, requested_value in requested_overrides.items():
        params[key] = coerce_param_value(params[key], requested_value)
        applied[key] = requested_value
    return applied


def apply_runner_param_overrides(
    runtime_config: dict[str, Any],
    requested_overrides: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Apply runner-declared parameter overrides directly to config keys."""
    specs = runner_config.get("param_overrides")
    if not isinstance(specs, dict) or not specs:
        return None

    unknown = sorted(set(requested_overrides) - set(str(key) for key in specs))
    if unknown:
        allowed = ", ".join(sorted(str(key) for key in specs)) or "<none>"
        raise ValueError(
            f"Unsupported config override(s): {', '.join(unknown)}. "
            f"Allowed params for this pipeline: {allowed}."
        )

    applied: dict[str, Any] = {}
    for key, requested_value in requested_overrides.items():
        spec = specs.get(key) or {}
        if isinstance(spec, str):
            target_key = spec
            default = runtime_config.get(target_key)
        elif isinstance(spec, dict):
            target_key = str(spec.get("config_key") or spec.get("wdl_key") or spec.get("key") or key)
            default = runtime_config.get(target_key, spec.get("default"))
        else:
            target_key = str(key)
            default = runtime_config.get(target_key)
        runtime_config[target_key] = coerce_param_value(default, requested_value)
        applied[str(key)] = requested_value
    return applied


def apply_runner_preset(
    runtime_config: dict[str, Any],
    requested_overrides: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    """Apply a runner preset selected by a required user-facing parameter."""
    requested = dict(requested_overrides)
    preset_param = str(runner_config.get("preset_param") or "").strip()
    presets = runner_config.get("presets")
    if not preset_param or not isinstance(presets, dict) or not presets:
        return requested

    param_specs = runner_config.get("param_overrides") or {}
    param_spec = param_specs.get(preset_param) if isinstance(param_specs, dict) else {}
    required = isinstance(param_spec, dict) and bool(param_spec.get("required"))
    selected = requested.get(preset_param)
    if selected in (None, ""):
        if required:
            choices = ", ".join(str(key) for key in presets)
            raise ValueError(
                f"Required pipeline parameter '{preset_param}' is missing. "
                f"Choose one of: {choices}."
            )
        return requested

    normalized = _normalize_preset_name(selected)
    matched_name = next(
        (str(name) for name in presets if _normalize_preset_name(name) == normalized),
        None,
    )
    if matched_name is None:
        choices = ", ".join(str(key) for key in presets)
        raise ValueError(
            f"Unsupported {preset_param} '{selected}'. Choose one of: {choices}."
        )
    preset_values = presets.get(matched_name)
    if not isinstance(preset_values, dict):
        raise ValueError(f"Pipeline preset '{matched_name}' must be a mapping.")
    runtime_config.update(copy.deepcopy(preset_values))
    requested[preset_param] = matched_name
    return requested


def _normalize_preset_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_config_overrides(config_overrides: dict[str, Any] | None) -> dict[str, Any]:
    if config_overrides is None:
        return {}
    if not isinstance(config_overrides, dict):
        raise ValueError("config_overrides must be a mapping.")
    return dict(config_overrides)


def coerce_param_value(existing: Any, requested: Any) -> Any:
    if isinstance(existing, bool) and isinstance(requested, str):
        return requested.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(existing, int) and not isinstance(existing, bool) and isinstance(requested, str):
        return int(requested)
    if isinstance(existing, float) and isinstance(requested, str):
        return float(requested)
    if isinstance(existing, list):
        if isinstance(requested, list):
            return requested
        if isinstance(requested, str) and "," in requested:
            return [item.strip() for item in requested.split(",") if item.strip()]
        return [requested]
    return requested
