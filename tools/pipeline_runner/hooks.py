"""Trusted per-pipeline adapters declared by approved runner folders."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from tools.pipeline_runner.paths import resolve_pipeline_file
from tools.pipeline_runner.types import PipelineContext


def prepare_runtime_config(
    context: PipelineContext,
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    """Let an approved pipeline translate BioAgent config into engine config."""
    module = _load_adapter(context, "runtime_adapter")
    if module is None:
        return runtime_config
    handler = getattr(module, "prepare_runtime_config", None)
    if not callable(handler):
        raise ValueError(
            f"Runtime adapter {module.__file__} does not define prepare_runtime_config()."
        )
    result = handler(context=context, runtime_config=runtime_config)
    if not isinstance(result, dict):
        raise ValueError("prepare_runtime_config() must return a configuration mapping.")
    return result


def finalize_nextflow_run(
    context: PipelineContext,
    runtime_config: dict[str, Any],
    output_records: list[dict[str, Any]],
    command: list[str],
    stdout: str,
    stderr: str,
) -> None:
    """Run an optional synchronous result summarizer after Nextflow succeeds."""
    module = _load_adapter(context, "post_run_adapter")
    if module is None:
        return
    handler = getattr(module, "finalize_nextflow_run", None)
    if not callable(handler):
        raise ValueError(
            f"Post-run adapter {module.__file__} does not define finalize_nextflow_run()."
        )
    handler(
        context=context,
        runtime_config=runtime_config,
        output_records=output_records,
        command=command,
        stdout=stdout,
        stderr=stderr,
    )


def _load_adapter(context: PipelineContext, setting: str) -> ModuleType | None:
    value = str(context.runner_config.get(setting) or "").strip()
    if not value:
        return None
    path = resolve_pipeline_file(
        context.pipeline_dir,
        value,
        fallback=value,
        label=setting.replace("_", " ").title(),
    )
    module_name = f"bioagent_pipeline_adapter_{context.pipeline_name}_{setting}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load pipeline adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
