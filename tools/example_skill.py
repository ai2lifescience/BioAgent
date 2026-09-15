"""Run a local diagnostic workflow that calls the echo tool and returns structured metadata. Use when the user asks to test skill calling, verify tool calling, run a demo skill, or check the registry."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.example_skill import example_skill as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def example_skill(
    ctx: RunContextWrapper[BioRunContext],
    message: Annotated[str, Field(description='Message to echo.')],
    tag: Annotated[str | None, Field(description='Optional test label.')] = None,
    uppercase: Annotated[bool, Field(description='Whether to uppercase the echoed message.')] = False,
) -> str:
    """Run a local diagnostic workflow that calls the echo tool and returns structured metadata. Use when the user asks to test skill calling, verify tool calling, run a demo skill, or check the registry."""
    return await run_workflow(ctx.context, 'example_skill', _workflow,
        {'message': message, 'tag': tag, 'uppercase': uppercase}, category='diagnostics',
        with_progress=False)
