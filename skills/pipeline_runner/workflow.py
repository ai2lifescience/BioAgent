"""Skill workflow for approved pipeline folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context
from tools.pipeline_runner.config import load_pipeline_config, load_runner_config
from tools.pipeline_runner.inputs import (
    default_input_slot,
    pipeline_input_specs,
    resolve_input_value,
    stringify_input_value,
    validate_input_path,
    validate_input_value,
)
from tools.pipeline_runner.paths import (
    resolve_pipeline_dir,
    resolve_pipeline_name,
    resolve_project_path,
)


DEFAULT_PIPELINE_NAME = "generic_shell"

SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "pipeline_runner",
        "description": (
            "Run an approved pipeline folder under pipelines/. The pipeline "
            "runner.yaml selects engine: shell, engine: snakemake, engine: nextflow, "
            "or engine: wdl. Use for controlled pipeline execution, including shell, "
            "Snakemake, Nextflow, and WDL examples."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Pipeline folder name under pipelines/.",
                    "default": DEFAULT_PIPELINE_NAME,
                },
                "input_path": {
                    "type": "string",
                    "description": (
                        "Optional runtime input file path, often from session uploads. "
                        "Overrides the base config input_path."
                    ),
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional pipeline output directory. Relative paths resolve under the per-run directory.",
                },
                "label": {
                    "type": "string",
                    "description": "Optional run label.",
                },
                "cores": {
                    "type": "integer",
                    "description": (
                        "Snakemake or Nextflow cores. Ignored for shell and WDL pipelines."
                    ),
                    "default": 1,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Run Snakemake dry-run, Nextflow preview, or WDL validation.",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum runtime in seconds.",
                },
                "input_overrides": {
                    "type": "object",
                    "description": "Map runner.yaml input slot names to runtime file paths.",
                },
                "config_overrides": {
                    "type": "object",
                    "description": "Pipeline-specific parameter overrides for keys under the base config params.",
                },
            },
            "additionalProperties": False,
        },
    },
}


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _clean_path(value: Any) -> str:
    return str(value or "").strip()


def _accepts_text(spec: dict[str, Any]) -> str:
    accepts = spec.get("accepts") or []
    return ", ".join(str(item) for item in accepts) if accepts else "any file"


def _input_line(item: dict[str, Any]) -> str:
    spec = item["spec"]
    label = spec.get("label") or item["slot"]
    config_key = spec.get("config_key") or item["slot"]
    return (
        f"- {label} (`{item['slot']}`, key `{config_key}`): "
        f"{_accepts_text(spec)}"
    )


def _input_example(
    pipeline_name: str,
    input_specs: dict[str, dict[str, Any]],
) -> str:
    if not input_specs:
        return f'Run pipeline with pipeline_name: {pipeline_name} input_path: "path/to/input.file"'
    parts = [f"Run pipeline with pipeline_name: {pipeline_name}"]
    for slot, spec in input_specs.items():
        if not spec.get("required"):
            continue
        suffixes = spec.get("accepts") or [".file"]
        suffix = str(suffixes[0])
        stem = str(spec.get("label") or slot).lower().replace(" ", "_")
        parts.append(f'{slot}: "path/to/{stem}{suffix}"')
    return " ".join(parts)


def _requested_input_record(item: dict[str, Any], reason: str) -> dict[str, Any]:
    spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
    slot = str(item.get("slot") or spec.get("name") or "").strip()
    config_key = str(spec.get("config_key") or slot).strip()
    record = {
        "slot": slot,
        "label": str(spec.get("label") or slot),
        "config_key": config_key,
        "accepts": list(spec.get("accepts") or []),
        "reason": reason,
    }
    if item.get("path"):
        record["path"] = str(item["path"])
    if item.get("reason"):
        record["message"] = str(item["reason"])
    return {key: value for key, value in record.items() if value not in (None, "", [])}


def _requested_inputs(
    missing: list[dict[str, Any]],
    invalid: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requested: list[dict[str, Any]] = []
    seen_slots: set[str] = set()
    for item, reason in [(item, "invalid") for item in invalid] + [(item, "missing") for item in missing]:
        record = _requested_input_record(item, reason)
        slot = str(record.get("slot") or "")
        if slot and slot in seen_slots:
            continue
        if slot:
            seen_slots.add(slot)
        requested.append(record)
    return requested


def _canonical_input_overrides(
    input_overrides: dict[str, Any] | None,
    input_specs: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    if not input_overrides:
        return {}, []
    if not isinstance(input_overrides, dict):
        return {}, ["input_overrides must be a mapping from input slot name to path."]

    aliases: dict[str, str] = {}
    for slot, spec in input_specs.items():
        aliases[slot.lower()] = slot
        config_key = str(spec.get("config_key") or "").strip().lower()
        label = str(spec.get("label") or "").strip().lower()
        if config_key:
            aliases[config_key] = slot
        if label:
            aliases[label] = slot

    canonical: dict[str, str] = {}
    errors: list[str] = []
    for raw_slot, raw_path in input_overrides.items():
        key = str(raw_slot or "").strip().lower()
        slot = aliases.get(key)
        if not slot:
            allowed = ", ".join(sorted(input_specs)) or "<none>"
            errors.append(f"Unknown input slot `{raw_slot}`. Allowed slots: {allowed}.")
            continue
        path = _clean_path(raw_path)
        if path:
            canonical[slot] = path
    return canonical, errors


def _resolve_supplied_inputs(
    input_path: str | None,
    input_overrides: dict[str, str],
    input_specs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved: dict[str, Any] = {}
    invalid: list[dict[str, Any]] = []

    for slot, path_text in input_overrides.items():
        spec = input_specs.get(slot) or {}
        config_key = str(spec.get("config_key") or slot)
        try:
            path = resolve_input_value(path_text, spec)
            validate_input_value(path, spec)
            resolved[config_key] = path
        except Exception as exc:
            invalid.append(
                {
                    "slot": slot,
                    "path": path_text,
                    "reason": str(exc),
                    "spec": spec,
                }
            )

    if input_path:
        slot = default_input_slot(input_specs)
        spec = input_specs.get(slot) or {"name": "input", "label": "Input file", "config_key": "input_path"}
        config_key = str(spec.get("config_key") or slot)
        try:
            path = resolve_project_path(input_path)
            validate_input_path(path, spec)
            resolved[config_key] = path
        except Exception as exc:
            invalid.append(
                {
                    "slot": slot,
                    "path": input_path,
                    "reason": str(exc),
                    "spec": spec,
                }
            )

    return resolved, invalid


def _required_input_check(
    pipeline_name: str,
    input_path: str | None,
    input_overrides: dict[str, Any] | None,
    config_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Return a user-facing input request when the pipeline is not ready to run."""
    resolved_name = resolve_pipeline_name(pipeline_name)
    pipeline_dir = resolve_pipeline_dir(resolved_name)
    runner_config, _runner_path = load_runner_config(pipeline_dir)
    _raw_config, raw_config_path = load_pipeline_config(pipeline_dir, runner_config)
    input_specs = pipeline_input_specs(runner_config)
    canonical_overrides, override_errors = _canonical_input_overrides(input_overrides, input_specs)
    supplied, invalid = _resolve_supplied_inputs(input_path, canonical_overrides, input_specs)
    invalid_config_keys = {
        str((item.get("spec") or {}).get("config_key") or item.get("slot") or "")
        for item in invalid
        if isinstance(item, dict)
    }

    missing: list[dict[str, Any]] = []
    for slot, spec in input_specs.items():
        if not spec.get("required"):
            continue
        config_key = str(spec.get("config_key") or slot)
        if config_key in supplied or config_key in invalid_config_keys:
            continue
        missing.append(
            {
                "slot": slot,
                "spec": spec,
                "reason": "No explicit path was provided. Pipeline defaults are not used by the BioAgent skill.",
            }
        )

    if not input_specs and not input_path:
        spec = {"name": "input", "label": "Input file", "config_key": "input_path", "accepts": []}
        missing.append({"slot": "input", "spec": spec, "reason": "No explicit input_path was provided."})

    if not (missing or invalid or override_errors):
        return None, canonical_overrides

    lines: list[str] = [
        f"Pipeline `{resolved_name}` needs input file information before it can run.",
        "BioAgent requires explicit runtime input paths and does not use pipeline default inputs.",
        "",
    ]
    if missing:
        lines.append("Missing required inputs:")
        lines.extend(_input_line(item) for item in missing)
        lines.append("")
    if invalid:
        lines.append("Invalid input paths:")
        for item in invalid:
            lines.append(f"- `{item['slot']}`: {item['path']} ({item['reason']})")
        lines.append("")
    if override_errors:
        lines.append("Invalid input slot names:")
        lines.extend(f"- {error}" for error in override_errors)
        lines.append("")
    lines.extend(
        [
            "Upload the needed file or provide a path in the request.",
            "",
            "Example:",
            _input_example(resolved_name, input_specs),
        ]
    )
    return (
        {
            "skill": "pipeline_runner",
            "status": "needs_input",
            "needs_input": True,
            "pipeline_name": resolved_name,
            "base_config_path": str(raw_config_path),
            "missing_inputs": missing,
            "invalid_inputs": invalid,
            "input_errors": override_errors,
            "requested_inputs": _requested_inputs(missing, invalid),
            "config_overrides": dict(config_overrides or {}),
            "answer": "\n".join(lines),
        },
        canonical_overrides,
    )


def _required_parameter_check(
    pipeline_name: str,
    config_overrides: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Request runner parameters that must be chosen explicitly by the user."""
    resolved_name = resolve_pipeline_name(pipeline_name)
    pipeline_dir = resolve_pipeline_dir(resolved_name)
    runner_config, _runner_path = load_runner_config(pipeline_dir)
    specs = runner_config.get("param_overrides") or {}
    if not isinstance(specs, dict):
        return None
    supplied = dict(config_overrides or {})
    missing: list[dict[str, Any]] = []
    invalid: list[str] = []
    for name, raw_spec in specs.items():
        spec = raw_spec if isinstance(raw_spec, dict) else {}
        if not spec.get("required"):
            continue
        value = supplied.get(str(name))
        choices = [str(item) for item in (spec.get("choices") or [])]
        if value in (None, ""):
            missing.append({"name": str(name), "label": spec.get("label") or name, "choices": choices})
            continue
        if choices and _normalized_choice(value) not in {_normalized_choice(item) for item in choices}:
            invalid.append(f"`{name}` must be one of: {', '.join(choices)} (received `{value}`).")
    if not missing and not invalid:
        return None
    lines = [f"Pipeline `{resolved_name}` needs a parameter choice before it can run.", ""]
    for item in missing:
        choices = ", ".join(item["choices"]) or "a supported value"
        lines.append(f"- {item['label']} (`{item['name']}`): choose {choices}")
    lines.extend(f"- {message}" for message in invalid)
    lines.extend(
        [
            "",
            f"Example: Run pipeline with pipeline_name: {resolved_name} pathogen: H1N1",
        ]
    )
    return {
        "skill": "pipeline_runner",
        "status": "needs_parameters",
        "needs_parameters": True,
        "pipeline_name": resolved_name,
        "required_parameters": missing,
        "parameter_errors": invalid,
        "answer": "\n".join(lines),
    }


def _normalized_choice(value: Any) -> str:
    return "".join(character for character in str(value or "").lower() if character.isalnum())


def pipeline_runner(
    pipeline_name: str = DEFAULT_PIPELINE_NAME,
    input_path: str | None = None,
    output_dir: str | None = None,
    label: str | None = None,
    cores: int | None = None,
    dry_run: bool = False,
    timeout: int | None = None,
    input_overrides: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "pipeline_runner")
    parameter_request = _required_parameter_check(pipeline_name, config_overrides)
    if parameter_request:
        return parameter_request
    input_request, canonical_input_overrides = _required_input_check(
        pipeline_name=pipeline_name,
        input_path=input_path,
        input_overrides=input_overrides,
        config_overrides=config_overrides,
    )
    if input_request:
        return input_request

    result = context.run_tool(
        "pipeline_runner",
        _drop_none(
            {
                "pipeline_name": pipeline_name,
                "input_path": input_path,
                "output_dir": output_dir,
                "label": label,
                "cores": cores,
                "dry_run": dry_run,
                "timeout": timeout,
                "input_overrides": canonical_input_overrides,
                "config_overrides": config_overrides,
                "artifact_dir": context.artifact_dir,
                "run_id": context.run_id,
            }
        ),
    )["result"]
    engine = str(result.get("engine", "pipeline"))
    answer = (
        f"{engine.title()} pipeline completed.\n"
        f"Status: {result.get('status', 'unknown')}\n"
        f"Pipeline: {result.get('pipeline_name', pipeline_name)}\n"
        f"Engine: {engine}\n"
        f"Dry run: {result.get('dry_run', False)}\n"
        "Results are ready in the web UI as download links; previews are hidden by default.\n"
        "If you want an interpreted view, ask: Collect and show all results from this pipeline run."
    )
    return {
        "skill": "pipeline_runner",
        "tool": "pipeline_runner",
        "answer": answer,
        **result,
        "presentation": "downloads_only",
    }
