"""Run the local diagnostic echo workflow.

Use only for testing tool calling, registry wiring, or the example skill. Do
not use for biological analysis or data retrieval.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import example_skill as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def example_skill(
    ctx: RunContextWrapper[BioRunContext],
    message: Annotated[str, Field(description='Message to echo.')],
    tag: Annotated[str | None, Field(description='Optional test label.')] = None,
    uppercase: Annotated[bool, Field(description='Whether to uppercase the echoed message.')] = False,
) -> str:
    """Run the diagnostic echo workflow for tool and registry checks."""
    return await run_workflow(ctx.context, 'example_skill', _workflow,
        {'message': message, 'tag': tag, 'uppercase': uppercase}, category='example_skill',
        with_progress=False)
