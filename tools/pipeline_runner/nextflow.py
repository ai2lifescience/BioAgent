"""Nextflow engine implementation for approved pipeline folders."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from tools.pipeline_runner.config import write_runtime_config
from tools.pipeline_runner.hooks import finalize_nextflow_run
from tools.pipeline_runner.outputs import (
    finalize_output_records,
    output_path_by_config_key,
)
from tools.pipeline_runner.paths import (
    assert_inside,
    read_json,
    resolve_pipeline_file,
    resolve_workflow_root,
)
from tools.pipeline_runner.types import PipelineContext


def run_nextflow_pipeline(
    context: PipelineContext,
    cores: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a Nextflow pipeline using its configured local workflow file."""
    resolved_cores = max(1, int(cores or context.runner_config.get("cores", 1)))
    workflow_root = resolve_workflow_root(context.pipeline_dir, context.runner_config)
    workflow_path = resolve_pipeline_file(
        workflow_root,
        str(context.runner_config.get("workflow") or "main.nf"),
        fallback="main.nf",
        label="Nextflow workflow",
    )
    config_path = _nextflow_config_path(context, workflow_root)
    work_dir = context.run_dir / "nextflow_work"
    engine_output_dir = context.run_dir / "nextflow_output"
    work_dir.mkdir(parents=True, exist_ok=True)
    engine_output_dir.mkdir(parents=True, exist_ok=True)

    runtime_config = write_runtime_config(
        context,
        {
            "cores": resolved_cores,
            "bioagent_config_path": str(context.run_dir / "config.runtime.yaml"),
            "nextflow_output_dir": str(engine_output_dir),
        },
    )
    entry = _nextflow_entry(context, runtime_config.config)
    profile = str(context.runner_config.get("profile") or "").strip()
    command = [*_nextflow_command()]
    if config_path is not None:
        command.extend(["-c", str(config_path)])
    command.extend(
        [
            "run",
            str(workflow_path),
            "-params-file",
            str(runtime_config.path),
            "-work-dir",
            str(work_dir),
            "-ansi-log",
            "false",
        ]
    )
    if profile:
        command.extend(["-profile", profile])
    if entry:
        command.extend(["-entry", entry])
    if bool(context.runner_config.get("resume", False)):
        command.append("-resume")
    command.extend(_trusted_nextflow_args(context))
    if dry_run:
        command.append("-preview")

    env = os.environ.copy()
    env["NXF_ANSI_LOG"] = "false"
    nextflow_version = str(context.runner_config.get("nextflow_version") or "").strip()
    if nextflow_version:
        env["NXF_VER"] = nextflow_version
    completed = subprocess.run(
        command,
        cwd=str(context.run_dir),
        env=env,
        text=True,
        capture_output=True,
        timeout=context.timeout,
        check=False,
    )
    if completed.returncode != 0:
        details = _compact_output(completed.stderr or completed.stdout)
        raise RuntimeError(
            f"nextflow pipeline failed with exit code {completed.returncode}: {details}"
        )

    if not dry_run:
        finalize_nextflow_run(
            context=context,
            runtime_config=runtime_config.config,
            output_records=runtime_config.output_records,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    if not dry_run:
        _copy_declared_outputs(runtime_config.output_records, engine_output_dir)
    if runtime_config.output_records:
        files, output_records = finalize_output_records(
            runtime_config.output_records,
            require_outputs=not dry_run,
        )
    else:
        output_records = []
        files = [] if dry_run else [
            str(path) for path in engine_output_dir.rglob("*") if path.is_file()
        ]

    metrics_path = output_path_by_config_key(
        output_records,
        "metrics_path",
        context.output_dir / "metrics.json",
    )
    report_path = output_path_by_config_key(
        output_records,
        "report_path",
        context.output_dir / "report.md",
    )
    return {
        "status": "ok",
        "pipeline": str(context.runner_config.get("name", context.pipeline_name)),
        "pipeline_name": context.pipeline_name,
        "engine": "nextflow",
        "dry_run": dry_run,
        "config_path": str(runtime_config.path),
        "runner_config_path": str(context.runner_config_path),
        "raw_config_path": str(context.raw_config_path),
        "base_config_path": str(context.raw_config_path),
        "nextflow_config_path": str(config_path or ""),
        "workflow_path": str(workflow_path),
        "workflow_root": str(workflow_root),
        "entry": entry,
        "profile": profile,
        "nextflow_version": nextflow_version,
        "staged_config_paths": runtime_config.staged_config_paths,
        "config_overrides": runtime_config.applied_config_overrides,
        "pipeline_dir": str(context.pipeline_dir),
        "input_path": str(context.input_path),
        "original_input_path": str(context.original_input_path),
        "session_input_path": str(context.session_input_path or ""),
        "input_staged": context.input_staged,
        "input_overrides": {
            key: str(path) for key, path in context.resolved_input_overrides.items()
        },
        "run_dir": str(context.run_dir),
        "output_dir": str(context.output_dir),
        "engine_output_dir": str(engine_output_dir),
        "work_dir": str(work_dir),
        "label": context.label,
        "cores": resolved_cores,
        "timeout": context.timeout,
        "returncode": completed.returncode,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "metrics_path": str(metrics_path),
        "report_path": str(report_path),
        "output_records": output_records,
        "files": [] if dry_run else files,
        "metrics": {} if dry_run else read_json(metrics_path),
    }


def _nextflow_config_path(
    context: PipelineContext,
    workflow_root: Path,
) -> Path | None:
    value = context.runner_config.get("nextflow_config") or context.runner_config.get(
        "nextflow_config_file"
    )
    if not value:
        conventional_path = workflow_root / "nextflow.config"
        return conventional_path.resolve() if conventional_path.is_file() else None
    return resolve_pipeline_file(
        workflow_root,
        str(value),
        fallback="nextflow.config",
        label="Nextflow config",
    )


def _nextflow_entry(
    context: PipelineContext,
    runtime_config: dict[str, Any],
) -> str:
    bioagent = runtime_config.get("bioagent")
    dynamic_entry = bioagent.get("entry") if isinstance(bioagent, dict) else None
    entry = str(dynamic_entry or context.runner_config.get("entry") or "").strip()
    if not entry:
        return ""
    allowed = [
        str(item).strip()
        for item in (context.runner_config.get("allowed_entries") or [])
        if str(item).strip()
    ]
    if allowed and entry not in allowed:
        raise ValueError(
            f"Nextflow entry '{entry}' is not approved for pipeline {context.pipeline_name}. "
            f"Allowed entries: {', '.join(allowed)}."
        )
    return entry


def _trusted_nextflow_args(context: PipelineContext) -> list[str]:
    """Return static Nextflow arguments declared by an approved runner folder."""
    value = context.runner_config.get("nextflow_args") or []
    if not isinstance(value, list):
        raise ValueError("runner.yaml nextflow_args must be a list.")
    args = [str(item) for item in value]
    if any(not item.strip() or "\x00" in item for item in args):
        raise ValueError("runner.yaml nextflow_args contains an invalid argument.")
    return args


def _copy_declared_outputs(
    output_records: list[dict[str, Any]],
    engine_output_dir: Path,
) -> None:
    """Copy published Nextflow outputs into BioAgent's declared artifact paths."""
    for record in output_records:
        target = Path(str(record.get("path") or ""))
        source_name = str(record.get("nextflow_output") or target.name).strip()
        if not source_name:
            continue
        source_value = Path(source_name)
        if source_value.is_absolute():
            raise ValueError("runner.yaml nextflow_output paths must be relative.")
        source = (engine_output_dir / source_value).resolve()
        assert_inside(source, engine_output_dir)
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def _nextflow_command() -> list[str]:
    executable = shutil.which("nextflow")
    if executable:
        return [executable]
    raise RuntimeError(
        "Nextflow is not installed. Install Nextflow and Java 17 or newer to run "
        "Nextflow pipelines."
    )


def _compact_output(value: str) -> str:
    lines = [line for line in str(value or "").splitlines() if line.strip()]
    return "\n".join(lines[-20:]) if lines else "<no Nextflow output>"
