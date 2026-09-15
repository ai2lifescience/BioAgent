"""Collect, summarize, and display outputs from the latest completed pipeline run in the current session. Use only when the user explicitly asks to collect, show, review, or summarize pipeline results."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.pipeline_results import pipeline_results as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def pipeline_results(
    ctx: RunContextWrapper[BioRunContext],
    pipeline_name: Annotated[str, Field(description='Optional pipeline folder name, such as generic_bio.')] = '',
    max_table_rows: Annotated[int, Field(ge=1, le=50)] = 10,
) -> str:
    """Collect, summarize, and display outputs from the latest completed pipeline run in the current session. Use only when the user explicitly asks to collect, show, review, or summarize pipeline results."""
    return await run_workflow(ctx.context, 'pipeline_results', _workflow,
        {'pipeline_name': pipeline_name, 'max_table_rows': max_table_rows}, category='pipeline',
        with_progress=False)
