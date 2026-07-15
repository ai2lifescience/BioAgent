"""Input declarations, validation, and staging for pipeline runs."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
from typing import Any

from tools.pipeline_runner.paths import (
    PROJECT_ROOT,
    resolve_pipeline_input_path,
    resolve_project_path,
    safe_label,
)
from tools.pipeline_runner.types import PipelineContext


def pipeline_input_specs(runner_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return normalized input slot specs declared by runner.yaml."""
    raw_inputs = runner_config.get("inputs") or {}
    items: list[tuple[str, Any]]
    if isinstance(raw_inputs, dict):
        items = [(str(name), value) for name, value in raw_inputs.items()]
    elif isinstance(raw_inputs, list):
        items = []
        for index, value in enumerate(raw_inputs, start=1):
            if not isinstance(value, dict):
                continue
            name = str(value.get("name") or value.get("slot") or f"input_{index}")
            items.append((name, value))
    else:
        return {}

    specs: dict[str, dict[str, Any]] = {}
    for name, value in items:
        if not isinstance(value, dict):
            value = {}
        slot = safe_label(name, "input")
        config_key = str(value.get("config_key") or value.get("wdl_key") or value.get("key") or slot).strip()
        if not config_key:
            continue
        accepts = value.get("accepts") or value.get("extensions") or []
        if isinstance(accepts, str):
            accepts = [accepts]
        specs[slot] = {
            "name": slot,
            "label": str(value.get("label") or slot),
            "config_key": config_key,
            "required": bool(value.get("required", False)),
            "accepts": normalize_suffix_list(accepts),
            "description": str(value.get("description") or ""),
            "multiple": bool(
                value.get("multiple")
                or value.get("array")
                or str(value.get("type") or "").strip().lower() in {"array", "file_array", "array[file]"}
            ),
        }
    return specs


def default_input_slot(input_specs: dict[str, dict[str, Any]]) -> str:
    for slot, spec in input_specs.items():
        if spec.get("config_key") == "input_path":
            return slot
    for slot, spec in input_specs.items():
        if spec.get("required"):
            return slot
    return next(iter(input_specs), "input")


def normalize_input_overrides(input_overrides: dict[str, Any] | None) -> dict[str, str]:
    if input_overrides is None:
        return {}
    if not isinstance(input_overrides, dict):
        raise ValueError("input_overrides must be a mapping from input slot to path.")
    return {
        safe_label(str(slot), "input"): str(path).strip()
        for slot, path in input_overrides.items()
        if str(path).strip()
    }


def resolve_input_overrides(
    input_overrides: dict[str, str],
    input_specs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for slot, path_value in input_overrides.items():
        spec = input_specs.get(slot)
        if spec is None:
            allowed = ", ".join(sorted(input_specs)) or "<none>"
            raise ValueError(f"Unknown pipeline input slot '{slot}'. Allowed slots: {allowed}.")
        config_key = str(spec.get("config_key") or slot)
        path = resolve_input_value(path_value, spec)
        validate_input_value(path, spec)
        resolved[config_key] = path
        records.append(
            {
                "slot": slot,
                "config_key": config_key,
                "path": stringify_input_value(path),
                "source": "input_overrides",
            }
        )
    return resolved, records


def resolve_input_value(value: Any, spec: dict[str, Any] | None = None) -> Any:
    """Resolve a pipeline input path or path list from a request/base config."""
    if spec and spec.get("multiple"):
        return [resolve_project_path(item) for item in split_input_paths(value)]
    if isinstance(value, list):
        if not value:
            return []
        return resolve_project_path(value[0])
    return resolve_project_path(str(value))


def split_input_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    if separator in text:
        return [item.strip() for item in text.split(separator) if item.strip()]
    return [text]


def validate_input_path(path: Path, spec: dict[str, Any] | None = None) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Pipeline input file not found: {path}")
    if path.is_dir() or not spec:
        return
    accepts = spec.get("accepts") or []
    if not accepts:
        return
    lower_name = path.name.lower()
    if not any(lower_name.endswith(str(suffix).lower()) for suffix in accepts):
        allowed = ", ".join(str(suffix) for suffix in accepts)
        raise ValueError(f"Input {path} does not match accepted suffixes for {spec.get('name')}: {allowed}.")


def validate_input_value(value: Any, spec: dict[str, Any] | None = None) -> None:
    if isinstance(value, list):
        if spec and spec.get("required") and not value:
            raise ValueError(f"Required pipeline input '{spec.get('name')}' has no files.")
        for path in value:
            validate_input_path(path, spec)
        return
    validate_input_path(value, spec)


def validate_declared_inputs(
    raw_config: dict[str, Any],
    input_specs: dict[str, dict[str, Any]],
    resolved_input_overrides: dict[str, Any],
    pipeline_dir: Path,
) -> None:
    for slot, spec in input_specs.items():
        config_key = str(spec.get("config_key") or slot)
        value = resolved_input_overrides.get(config_key) or raw_config.get(config_key)
        if not value:
            if spec.get("required"):
                raise ValueError(f"Required pipeline input '{slot}' is missing config key '{config_key}'.")
            continue
        if isinstance(value, list):
            paths = [
                item if isinstance(item, Path) else resolve_pipeline_input_path(str(item), pipeline_dir)
                for item in value
            ]
            validate_input_value(paths, spec)
        else:
            path = value if isinstance(value, Path) else resolve_pipeline_input_path(str(value), pipeline_dir)
            validate_input_path(path, spec)


def normalize_suffix_list(values: Any) -> list[str]:
    suffixes: list[str] = []
    for value in values or []:
        suffix = str(value or "").strip().lower()
        if not suffix:
            continue
        suffixes.append(suffix if suffix.startswith(".") else f".{suffix}")
    return suffixes


def stringify_input_value(value: Any) -> Any:
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value)


def staged_input_records(context: PipelineContext) -> list[dict[str, Any]]:
    if not context.input_staged or context.session_input_path is None:
        return []
    return [
        {
            "config_field": "input_path",
            "original_input_path": str(context.original_input_path),
            "session_input_path": str(context.session_input_path),
            "staged": True,
        }
    ]


def rewrite_top_level_path_fields(
    runtime_config: dict[str, Any],
    context: PipelineContext,
    skip_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve extra top-level *_path fields relative to project or pipeline dir."""
    records: list[dict[str, Any]] = []
    skipped = set(skip_keys or set())
    for key, value in list(runtime_config.items()):
        if key in skipped:
            continue
        if key in {"input_path", "output_dir"}:
            continue
        if not key.endswith("_path") or not isinstance(value, str) or not value.strip():
            continue
        source = resolve_pipeline_input_path(value, context.pipeline_dir)
        if not source.exists():
            continue
        target = source
        if context.stage_input and context.artifact_dir:
            target = stage_pipeline_input(source, context.artifact_dir) or source
        runtime_config[key] = str(target)
        if target == source:
            continue
        records.append(
            {
                "config_field": key,
                "original_input_path": str(source),
                "session_input_path": str(target),
                "staged": target != source,
            }
        )
    return records


def stage_pipeline_input(input_path: Path, artifact_dir: str | Path | None) -> Path | None:
    """Make the pipeline input easy to find and reuse in the session."""
    if not artifact_dir:
        return None

    source = input_path.resolve()
    artifact_base = Path(artifact_dir)
    if not artifact_base.is_absolute():
        artifact_base = PROJECT_ROOT / artifact_base
    artifact_base = artifact_base.resolve()

    try:
        source.relative_to(artifact_base)
        return source
    except ValueError:
        pass

    input_dir = artifact_base / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    destination = input_dir / session_input_filename(source)
    if destination.exists():
        return destination.resolve()

    if source.is_dir():
        try:
            os.symlink(source, destination, target_is_directory=True)
        except OSError:
            shutil.copytree(source, destination)
        return destination.resolve()

    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination.resolve()


def session_input_filename(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha1(
        f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:10]
    safe_stem = safe_label(path.stem, "input")
    return f"{safe_stem}-{digest}{path.suffix}"
