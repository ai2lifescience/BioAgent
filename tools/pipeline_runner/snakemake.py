"""Snakemake engine implementation for approved pipeline folders."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from typing import Any

from tools.pipeline_runner.config import write_runtime_config
from tools.pipeline_runner.outputs import finalize_output_records, output_path_by_config_key
from tools.pipeline_runner.paths import (
    PROJECT_ROOT,
    read_json,
    resolve_pipeline_file,
)
from tools.pipeline_runner.types import PipelineContext


def run_snakemake_pipeline(
    context: PipelineContext,
    cores: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a Snakemake pipeline using its configured relative Snakefile."""
    resolved_cores = max(1, int(cores or context.runner_config.get("cores", 1)))
    snakefile = resolve_pipeline_file(
        context.pipeline_dir,
        str(context.runner_config.get("snakefile", "Snakefile")),
        fallback="Snakefile",
        label="Snakemake file",
    )
    runtime_config = write_runtime_config(context, {"cores": resolved_cores})
    command = [
        *_snakemake_command(),
        "--cores",
        str(resolved_cores),
        "--snakefile",
        str(snakefile),
        "--configfile",
        str(runtime_config.path),
    ]
    if dry_run:
        command.append("--dry-run")

    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        timeout=context.timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"snakemake pipeline failed with exit code {completed.returncode}: {completed.stderr}"
        )

    metrics_path = output_path_by_config_key(
        runtime_config.output_records,
        "metrics_path",
        context.output_dir / "metrics.json",
    )
    report_path = output_path_by_config_key(
        runtime_config.output_records,
        "report_path",
        context.output_dir / "report.md",
    )
    normalized_path = output_path_by_config_key(
        runtime_config.output_records,
        "normalized_fasta_path",
        context.output_dir / "normalized.txt",
    )
    if runtime_config.output_records:
        files, output_records = finalize_output_records(
            runtime_config.output_records,
            require_outputs=not dry_run,
        )
    else:
        output_records = []
        files = [] if dry_run else [
            str(path)
            for path in (metrics_path, report_path, normalized_path)
            if path.exists()
        ]
    return {
        "status": "ok",
        "pipeline": str(context.runner_config.get("name", context.pipeline_name)),
        "pipeline_name": context.pipeline_name,
        "engine": "snakemake",
        "dry_run": dry_run,
        "config_path": str(runtime_config.path),
        "runner_config_path": str(context.runner_config_path),
        "raw_config_path": str(context.raw_config_path),
        "base_config_path": str(context.raw_config_path),
        "staged_config_paths": runtime_config.staged_config_paths,
        "config_overrides": runtime_config.applied_config_overrides,
        "pipeline_dir": str(context.pipeline_dir),
        "input_path": str(context.input_path),
        "original_input_path": str(context.original_input_path),
        "session_input_path": str(context.session_input_path or ""),
        "input_staged": context.input_staged,
        "input_overrides": {key: str(path) for key, path in context.resolved_input_overrides.items()},
        "run_dir": str(context.run_dir),
        "output_dir": str(context.output_dir),
        "label": context.label,
        "cores": resolved_cores,
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


def _snakemake_command() -> list[str]:
    executable = shutil.which("snakemake")
    if executable:
        return [executable]
    if importlib.util.find_spec("snakemake"):
        return [sys.executable, "-m", "snakemake"]
    raise RuntimeError(
        "Snakemake is not installed. Install it to run the Snakemake pipeline."
    )
