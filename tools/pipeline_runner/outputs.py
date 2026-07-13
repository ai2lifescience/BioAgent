"""Output declarations and validation for pipeline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.pipeline_runner.paths import resolve_pipeline_output_path, safe_label
from tools.pipeline_runner.types import PipelineContext


def pipeline_output_specs(runner_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return normalized output file specs declared by runner.yaml."""
    raw_outputs = runner_config.get("outputs") or {}
    items: list[tuple[str, Any]]
    if isinstance(raw_outputs, dict):
        items = [(str(name), value) for name, value in raw_outputs.items()]
    elif isinstance(raw_outputs, list):
        items = []
        for index, value in enumerate(raw_outputs, start=1):
            if not isinstance(value, dict):
                continue
            name = str(value.get("name") or value.get("slot") or f"output_{index}")
            items.append((name, value))
    else:
        return {}

    specs: dict[str, dict[str, Any]] = {}
    for name, value in items:
        if isinstance(value, str):
            value = {"path": value}
        if not isinstance(value, dict):
            value = {}
        slot = safe_label(name, "output")
        config_key = str(value.get("config_key") or value.get("key") or "").strip()
        default_path = (
            value.get("default")
            or value.get("target")
            or value.get("path")
            or value.get("file")
        )
        if not config_key and not default_path:
            continue
        specs[slot] = {
            "name": slot,
            "label": str(value.get("label") or slot),
            "config_key": config_key,
            "default": str(default_path).strip() if default_path else "",
            "kind": str(value.get("kind") or "file"),
            "required": bool(value.get("required", True)),
            "description": str(value.get("description") or ""),
            "wdl_output": str(value.get("wdl_output") or ""),
        }
    return specs


def rewrite_output_config_fields(
    runtime_config: dict[str, Any],
    context: PipelineContext,
) -> list[dict[str, Any]]:
    """Rewrite declared output config keys to per-run artifact paths."""
    records: list[dict[str, Any]] = []
    for name, spec in pipeline_output_specs(context.runner_config).items():
        declared_config_key = str(spec.get("config_key") or "")
        default_path = str(spec.get("default") or "").strip()
        raw_value = (runtime_config.get(declared_config_key) if declared_config_key else None) or default_path
        if not raw_value:
            if spec.get("required"):
                raise ValueError(
                    f"Required pipeline output '{name}' is missing a target path "
                    f"and no default was declared in {context.runner_config_path}."
                )
            continue

        output_path = resolve_pipeline_output_path(str(raw_value), context.run_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if declared_config_key:
            runtime_config[declared_config_key] = str(output_path)
        records.append(
            {
                "name": name,
                "label": spec.get("label") or name,
                "config_key": declared_config_key,
                "path": str(output_path),
                "raw_path": str(raw_value),
                "kind": spec.get("kind") or "file",
                "required": bool(spec.get("required", True)),
                "wdl_output": spec.get("wdl_output") or "",
            }
        )
    return records


def finalize_output_records(
    output_records: list[dict[str, Any]],
    require_outputs: bool = True,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return existing declared output files and records annotated with existence."""
    files: list[str] = []
    finalized: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for record in output_records:
        item = dict(record)
        path = Path(str(item.get("path") or ""))
        exists = path.exists()
        item["exists"] = exists
        if exists:
            files.append(str(path))
        elif require_outputs and item.get("required", True):
            missing_required.append(f"{item.get('name') or item.get('config_key')}: {path}")
        finalized.append(item)

    if missing_required:
        raise FileNotFoundError(
            "Required pipeline output file(s) were not created: "
            + "; ".join(missing_required)
        )
    return files, finalized


def output_path_by_config_key(
    output_records: list[dict[str, Any]],
    config_key: str,
    fallback: Path,
) -> Path:
    """Find a declared output path by config key, with legacy fallback."""
    for record in output_records:
        if record.get("config_key") == config_key and record.get("path"):
            return Path(str(record["path"]))
    return fallback


def default_pipeline_output_dir(
    runner_config: dict[str, Any],
    raw_config: dict[str, Any],
) -> str:
    return str(runner_config.get("default_output_dir") or raw_config.get("output_dir") or "output")
