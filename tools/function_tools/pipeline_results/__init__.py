"""Collect and summarize outputs from a completed pipeline run.

Use only when the user asks to review, show, collect, or summarize pipeline
results. Do not use to start a pipeline; use ``pipeline_runner`` instead.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import pipeline_results as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def pipeline_results(
    ctx: RunContextWrapper[BioRunContext],
    pipeline_name: Annotated[str, Field(description='Optional pipeline folder name, such as generic_bio.')] = '',
    max_table_rows: Annotated[int, Field(ge=1, le=50)] = 10,
) -> str:
    """Collect and summarize outputs from the latest completed pipeline run.

    Use when the user asks to collect, review, show, or summarize pipeline
    results in the current session. Collects existing outputs and produces
    summaries or bundles. Use pipeline_runner to execute a pipeline.
    """
    return await run_workflow(ctx.context, 'pipeline_results', _workflow,
        {'pipeline_name': pipeline_name, 'max_table_rows': max_table_rows}, category='pipeline_results',
        with_progress=False)
