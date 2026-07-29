"""Translate BioAgent requests into native Metagenomics-Toolkit parameters."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from tools.pipeline_config import load_yaml_config
from tools.pipeline_runner.types import PipelineContext


FULL_ENTRY = "wFullPipeline"
OUTPUT_CONFIG_KEYS = {"output", "logDir", "report_path", "metrics_path"}


def prepare_runtime_config(
    context: PipelineContext,
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    """Load a native params file and select a full or one-module entry."""
    integration_params = runtime_config.get("params")
    if not isinstance(integration_params, dict):
        raise ValueError("Metagenomics adapter configuration is missing params.")

    execution_mode = _normalize_name(integration_params.get("execution_mode") or "full")
    module_value = integration_params.get("module")
    if isinstance(module_value, (list, tuple, set, dict)):
        raise ValueError("Standalone execution accepts exactly one named module.")
    module_name = _normalize_name(module_value)
    if any(separator in str(module_value or "") for separator in (",", ";")):
        raise ValueError("Standalone execution accepts exactly one named module.")

    toolkit_config = load_yaml_config(context.input_path)
    if not isinstance(toolkit_config, dict) or not toolkit_config:
        raise ValueError("Toolkit parameter YAML must contain a non-empty mapping.")

    if execution_mode == "full":
        if module_name:
            raise ValueError("module must be omitted when execution_mode is full.")
        _validate_full_config(toolkit_config)
        entry = FULL_ENTRY
        selected_module = ""
    elif execution_mode == "standalone":
        if not module_name:
            raise ValueError(
                "execution_mode standalone requires exactly one module name."
            )
        catalog = _load_catalog(context.pipeline_dir)
        module = catalog.get(module_name)
        if module is None:
            allowed = ", ".join(sorted(catalog))
            raise ValueError(
                f"Unsupported standalone module '{module_name}'. Allowed modules: {allowed}."
            )
        _validate_standalone_config(toolkit_config, module_name, module)
        entry = str(module["entry"])
        selected_module = module_name
    else:
        raise ValueError("execution_mode must be 'full' or 'standalone'.")

    for key in OUTPUT_CONFIG_KEYS:
        toolkit_config.pop(key, None)
    toolkit_config["publishDirMode"] = "copy"
    toolkit_config["bioagent"] = {
        "entry": entry,
        "execution_mode": execution_mode,
        "module": selected_module,
        "params_file": str(context.input_path),
    }
    return toolkit_config


def finalize_nextflow_run(
    context: PipelineContext,
    runtime_config: dict[str, Any],
    output_records: list[dict[str, Any]],
    command: list[str],
    stdout: str,
    stderr: str,
) -> None:
    """Create small stable BioAgent summaries for the toolkit's output tree."""
    paths = {
        str(record.get("config_key") or ""): Path(str(record.get("path") or ""))
        for record in output_records
    }
    results_dir = paths.get("output")
    logs_dir = paths.get("logDir")
    metrics_path = paths.get("metrics_path")
    report_path = paths.get("report_path")
    if metrics_path is None or report_path is None:
        raise ValueError("Metagenomics output contract is missing report or metrics paths.")

    bioagent = runtime_config.get("bioagent")
    metadata = bioagent if isinstance(bioagent, dict) else {}
    trace_summary = _validate_nextflow_trace(logs_dir)
    result_files = _file_count(results_dir)
    log_files = _file_count(logs_dir)
    metrics = {
        "status": "ok",
        "pipeline": "metagenomics_toolkit",
        "execution_mode": str(metadata.get("execution_mode") or ""),
        "module": str(metadata.get("module") or ""),
        "entry": str(metadata.get("entry") or ""),
        "params_file": str(metadata.get("params_file") or context.input_path),
        "result_files": result_files,
        "log_files": log_files,
        **trace_summary,
        "nextflow_stdout_lines": len(stdout.splitlines()),
        "nextflow_stderr_lines": len(stderr.splitlines()),
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    module_label = metrics["module"] or "full pipeline"
    report = [
        "# Metagenomics-Toolkit Run",
        "",
        f"- Status: {metrics['status']}",
        f"- Execution mode: {metrics['execution_mode']}",
        f"- Module: {module_label}",
        f"- Nextflow entry: {metrics['entry']}",
        f"- Parameter file: {metrics['params_file']}",
        f"- Result files: {result_files}",
        f"- Log files: {log_files}",
        f"- Successful Nextflow tasks: {metrics['successful_tasks']}",
        f"- Nextflow trace: {metrics['trace_path']}",
        f"- Results directory: {results_dir or ''}",
        f"- Logs directory: {logs_dir or ''}",
        "",
        "## Command",
        "",
        "```text",
        " ".join(command),
        "```",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")


def _load_catalog(pipeline_dir: Path) -> dict[str, dict[str, Any]]:
    raw = load_yaml_config(pipeline_dir / "module_catalog.yaml")
    modules = raw.get("modules") if isinstance(raw, dict) else None
    if not isinstance(modules, dict) or not modules:
        raise ValueError("Metagenomics module catalog is empty or invalid.")
    catalog: dict[str, dict[str, Any]] = {}
    for name, value in modules.items():
        if not isinstance(value, dict) or not value.get("entry") or not value.get("step"):
            raise ValueError(f"Invalid module catalog entry: {name}")
        catalog[_normalize_name(name)] = value
    return catalog


def _validate_full_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("input"), dict) or not config["input"]:
        raise ValueError("Full execution requires a non-empty top-level input mapping.")
    if not isinstance(config.get("steps"), dict) or not config["steps"]:
        raise ValueError("Full execution requires a non-empty top-level steps mapping.")


def _validate_standalone_config(
    config: dict[str, Any],
    module_name: str,
    module: dict[str, Any],
) -> None:
    steps = config.get("steps")
    if not isinstance(steps, dict) or not steps:
        raise ValueError("Standalone execution requires a non-empty steps mapping.")
    expected_step = str(module["step"])
    actual_steps = set(str(key) for key in steps)
    if actual_steps != {expected_step}:
        actual = ", ".join(sorted(actual_steps)) or "<none>"
        raise ValueError(
            f"Standalone module '{module_name}' requires steps to contain only "
            f"'{expected_step}' (received: {actual})."
        )


def _normalize_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace(" ", "_")


def _file_count(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def _validate_nextflow_trace(logs_dir: Path | None) -> dict[str, Any]:
    """Reject task failures that the upstream retry policy ultimately ignores."""
    if logs_dir is None or not logs_dir.is_dir():
        raise RuntimeError("MGTK did not create its declared Nextflow log directory.")
    traces = sorted(
        logs_dir.glob("trace*.tsv"),
        key=lambda path: path.stat().st_mtime_ns,
    )
    if not traces:
        raise RuntimeError(f"MGTK did not create a Nextflow trace in {logs_dir}.")
    trace_path = traces[-1]
    with trace_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    failed = [
        row
        for row in rows
        if str(row.get("status") or "").strip().upper() in {"FAILED", "ABORTED"}
    ]
    if failed:
        details: list[str] = []
        for row in failed:
            process = str(row.get("process") or "<unknown process>")
            exit_code = str(row.get("exit") or "?")
            item = f"{process} (exit {exit_code})"
            if item not in details:
                details.append(item)
        raise RuntimeError(
            "MGTK task failure(s) were ignored by the upstream retry policy: "
            + "; ".join(details[:10])
            + f". Inspect {trace_path}."
        )

    successful = [
        row
        for row in rows
        if str(row.get("status") or "").strip().upper() in {"COMPLETED", "CACHED"}
    ]
    module_tasks = [
        row
        for row in successful
        if not str(row.get("process") or "").endswith(":pConfigUpload")
    ]
    if not module_tasks:
        raise RuntimeError(
            "MGTK completed without a successful module task; only configuration "
            f"outputs were produced. Inspect {trace_path}."
        )
    return {
        "trace_path": str(trace_path),
        "successful_tasks": len(successful),
        "module_tasks": len(module_tasks),
        "failed_tasks": 0,
    }
