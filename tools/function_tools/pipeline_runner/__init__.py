"""Run one approved pipeline under ``pipelines/``.

Use for controlled shell, Snakemake, Nextflow, or WDL execution. This tool
has side effects and requires approval. Use ``pipeline_results`` afterward
when the user asks to review outputs.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import pipeline_runner as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=False, failure_error_function=tool_error, needs_approval=True, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=3600)
async def pipeline_runner(
    ctx: RunContextWrapper[BioRunContext],
    pipeline_name: Annotated[str, Field(description='Pipeline folder name under pipelines/.')] = 'generic_shell',
    input_path: Annotated[str | None, Field(description='Optional runtime input file path, often from session uploads. Overrides the base config input_path.')] = None,
    output_dir: Annotated[str | None, Field(description='Optional pipeline output directory. Relative paths resolve under the per-run directory.')] = None,
    label: Annotated[str | None, Field(description='Optional run label.')] = None,
    cores: Annotated[int | None, Field(description='Snakemake or Nextflow cores. Ignored for shell and WDL pipelines.')] = None,
    dry_run: Annotated[bool, Field(description='Run Snakemake dry-run, Nextflow preview, or WDL validation.')] = False,
    timeout: Annotated[int | None, Field(description='Maximum runtime in seconds.')] = None,
    input_overrides: Annotated[dict[str, Any] | None, Field(description='Map runner.yaml input slot names to runtime file paths.')] = None,
    config_overrides: Annotated[dict[str, Any] | None, Field(description='Pipeline-specific parameter overrides for keys under the base config params.')] = None,
) -> str:
    """Run one approved pipeline with the selected engine.

    Use to execute or validate a named pipeline folder under pipelines/ with
    its configured shell, Snakemake, Nextflow, or WDL engine. Execution writes
    files and requires SDK approval. Use pipeline_results to review an
    existing run; do not rerun a pipeline merely to show its outputs.
    """
    return await run_workflow(ctx.context, 'pipeline_runner', _workflow,
        {'pipeline_name': pipeline_name, 'input_path': input_path, 'output_dir': output_dir, 'label': label, 'cores': cores, 'dry_run': dry_run, 'timeout': timeout, 'input_overrides': input_overrides, 'config_overrides': config_overrides}, category='pipeline_runner',
        with_progress=False)
