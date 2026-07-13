"""Minimal WDL runner for approved pipeline folders."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

from tools.pipeline_runner.config import write_runtime_config
from tools.pipeline_runner.inputs import pipeline_input_specs
from tools.pipeline_runner.outputs import finalize_output_records
from tools.pipeline_runner.paths import (
    PROJECT_ROOT,
    read_json,
    resolve_pipeline_file,
    resolve_pipeline_input_path,
)
from tools.pipeline_runner.types import PipelineContext
from tools.pipeline_runner.wdl_options import write_options_runtime_json


def run_wdl_pipeline(
    context: PipelineContext,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a WDL pipeline with miniwdl."""
    workflow_path = resolve_pipeline_file(
        context.pipeline_dir,
        str(context.runner_config.get("workflow") or "workflow.wdl"),
        fallback="workflow.wdl",
        label="WDL workflow",
    )
    runtime_config = write_runtime_config(context)
    inputs_path = write_wdl_inputs(context)
    options_path = write_wdl_options(context)
    engine_dir = context.run_dir / "wdl_engine"
    engine_dir.mkdir(parents=True, exist_ok=True)
    outputs_json = context.run_dir / "wdl.outputs.json"

    if dry_run:
        command = [miniwdl_executable(), "check", str(workflow_path)]
    else:
        command = [
            miniwdl_executable(),
            "run",
            "--dir",
            str(engine_dir),
            "-o",
            str(outputs_json),
            "--no-color",
            str(workflow_path),
            "-i",
            str(inputs_path),
        ]

    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        timeout=context.timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(miniwdl_error(completed))

    if not dry_run:
        copy_declared_outputs(runtime_config.output_records, load_outputs(outputs_json))

    files, output_records = finalize_output_records(
        runtime_config.output_records,
        require_outputs=not dry_run,
    )
    metrics_path = output_path_by_name(output_records, "metrics")
    report_path = output_path_by_name(output_records, "report")
    return {
        "status": "ok",
        "pipeline": str(context.runner_config.get("name", context.pipeline_name)),
        "pipeline_name": context.pipeline_name,
        "engine": "wdl",
        "wdl_engine": "miniwdl",
        "dry_run": dry_run,
        "config_path": str(runtime_config.path),
        "inputs_path": str(inputs_path),
        "options_path": str(options_path) if options_path else "",
        "runner_config_path": str(context.runner_config_path),
        "raw_config_path": str(context.raw_config_path),
        "workflow_path": str(workflow_path),
        "input_path": str(context.input_path),
        "original_input_path": str(context.original_input_path),
        "session_input_path": str(context.session_input_path or ""),
        "input_staged": context.input_staged,
        "input_overrides": {key: str(path) for key, path in context.resolved_input_overrides.items()},
        "run_dir": str(context.run_dir),
        "output_dir": str(context.output_dir),
        "engine_dir": str(engine_dir),
        "label": context.label,
        "returncode": completed.returncode,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "metrics_path": str(metrics_path) if metrics_path else "",
        "report_path": str(report_path) if report_path else "",
        "output_records": output_records,
        "files": [] if dry_run else files,
        "metrics": {} if dry_run or not metrics_path else read_json(metrics_path),
    }


def write_wdl_inputs(context: PipelineContext) -> Path:
    """Write miniwdl input JSON from inputs.json and selected runtime files."""
    inputs = dict(context.raw_config)
    for key, path in context.resolved_input_overrides.items():
        inputs[key] = str(path)

    for spec in pipeline_input_specs(context.runner_config).values():
        key = str(spec.get("config_key") or "")
        value = inputs.get(key)
        if not key or not value:
            continue
        resolved = resolve_pipeline_input_path(str(value), context.pipeline_dir)
        if resolved.exists():
            inputs[key] = str(resolved)

    path = context.run_dir / "inputs.runtime.json"
    path.write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
    return path


def write_wdl_options(context: PipelineContext) -> Path | None:
    """Write optional WDL options JSON into the run directory."""
    value = context.runner_config.get("options_json") or context.runner_config.get("options_file")
    if not value:
        return None
    source = resolve_pipeline_file(
        context.pipeline_dir,
        str(value),
        fallback="options.json",
        label="WDL options file",
    )
    target = context.run_dir / "options.runtime.json"
    return write_options_runtime_json(source, target, context.run_dir)


def load_outputs(path: Path) -> dict[str, Any]:
    """Load the output map written by `miniwdl run -o`."""
    if not path.exists():
        return {}
    value = read_json(path)
    outputs = value.get("outputs") if isinstance(value.get("outputs"), dict) else value
    return outputs if isinstance(outputs, dict) else {}


def copy_declared_outputs(
    output_records: list[dict[str, Any]],
    output_map: dict[str, Any],
) -> None:
    """Copy WDL outputs into the BioAgent-declared artifact paths."""
    for record in output_records:
        target = Path(str(record.get("path") or ""))
        if not target or target.exists():
            continue
        source = output_source(record, output_map)
        if source is None or not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def output_source(record: dict[str, Any], output_map: dict[str, Any]) -> Path | None:
    wdl_output = str(record.get("wdl_output") or "")
    short_name = wdl_output.split(".")[-1] if wdl_output else str(record.get("name") or "")
    for key, value in output_map.items():
        if key != wdl_output and key.split(".")[-1] != short_name:
            continue
        return path_from_output_value(value)
    return None


def path_from_output_value(value: Any) -> Path | None:
    if isinstance(value, dict):
        value = value.get("path") or value.get("location") or value.get("value")
    if isinstance(value, list):
        return path_from_output_value(value[0]) if value else None
    if not isinstance(value, str) or not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(parsed.path).resolve()
    if parsed.scheme:
        return None
    return Path(value).resolve()


def output_path_by_name(output_records: list[dict[str, Any]], name: str) -> Path | None:
    for record in output_records:
        if record.get("name") == name and record.get("path"):
            return Path(str(record["path"]))
    return None


def miniwdl_executable() -> str:
    executable = shutil.which("miniwdl")
    if executable:
        return executable
    raise RuntimeError("miniwdl is not installed. Install it with `pip install miniwdl`.")


def miniwdl_error(completed: subprocess.CompletedProcess[str]) -> str:
    output = str(completed.stderr or completed.stdout or "")
    if docker_unavailable(output):
        return (
            "WDL pipeline failed: miniwdl could not connect to Docker. "
            "Start Docker, or configure your miniwdl environment to use another runtime backend."
        )
    if docker_image_unavailable(output):
        return (
            "WDL pipeline failed: Docker could not resolve or pull the WDL task image. "
            "Pull the image manually, fix Docker registry/network access, or set a local image "
            "in the task runtime block of workflow.wdl."
        )
    details = compact_output(output)
    return f"WDL pipeline failed with exit code {completed.returncode}: {details}"


def docker_unavailable(text: str) -> bool:
    return (
        "DockerException" in text
        or "Error while fetching server API version" in text
        or "docker.errors.DockerException" in text
    )


def docker_image_unavailable(text: str) -> bool:
    return (
        "images/create" in text
        or "failed to resolve reference" in text
        or "No such image" in text
        or "docker.errors.ImageNotFound" in text
        or "docker.errors.APIError" in text and "image" in text.lower()
    )


def compact_output(text: str) -> str:
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    return "\n".join(lines[-20:]) if lines else "<no miniwdl output>"
