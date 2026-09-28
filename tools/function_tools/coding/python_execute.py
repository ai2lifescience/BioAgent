"""Execute generated Python in the bounded workspace runner."""
from __future__ import annotations

from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.python_runner import execute_python
from tools.infrastructure.tool_support.artifacts import output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class PythonExecutionResult(FunctionContract):
    execution_id: str
    script_path: str
    returncode: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    duration_ms: int
    output_paths: list[str]
    missing_outputs: list[str]
    code_sha256: str
    summary: str


def _operation(*, code, input_paths=None, output_paths=None, timeout_seconds=60, context):
    import asyncio

    data, files = asyncio.run(execute_python(
        context,
        code=code,
        input_paths=input_paths,
        output_paths=output_paths,
        timeout_seconds=timeout_seconds,
    ))
    if data["timed_out"]:
        return {
            "status": "error",
            "data": data,
            "files": files,
            "evidence": [],
            "error": {"code": "PYTHON_TIMEOUT", "message": data["summary"]},
        }
    if data["returncode"] != 0:
        return {
            "status": "error",
            "data": data,
            "files": files,
            "evidence": [],
            "error": {"code": "PYTHON_EXECUTION_FAILED", "message": data["summary"]},
        }
    if data["missing_outputs"]:
        return {
            "status": "error",
            "data": data,
            "files": files,
            "evidence": [],
            "error": {"code": "PYTHON_OUTPUT_MISSING", "message": data["summary"]},
        }
    return output(data, *files)


@bio_function_tool(timeout=180, needs_approval=True)
async def python_execute(
    ctx: RunContextWrapper[AgentRunContext],
    code: Annotated[
        str,
        Field(
            min_length=1,
            max_length=256 * 1024,
            description="Complete Python source to execute in the bounded workspace runner.",
        ),
    ],
    input_paths: Annotated[
        list[str],
        Field(
            max_length=16,
            description=(
                "Optional workspace-relative files staged under inputs/. "
                "The BIOAGENT_INPUTS_JSON environment variable maps each original path to its staged path."
            ),
        ),
    ] = [],
    output_paths: Annotated[
        list[str],
        Field(
            max_length=64,
            description=(
                "Expected output paths relative to the execution directory; generated code should write there. "
                "Omit to collect created files."
            ),
        ),
    ] = [],
    timeout_seconds: Annotated[int, Field(ge=1, le=120, description="Maximum execution time in seconds.")] = 60,
) -> FunctionResult[PythonExecutionResult]:
    """Run generated Python after explicit approval and return verified artifacts."""
    return await invoke(
        ctx.context,
        "python_execute",
        _operation,
        {
            "code": code,
            "input_paths": input_paths,
            "output_paths": output_paths,
            "timeout_seconds": timeout_seconds,
        },
        FunctionResult[PythonExecutionResult],
    )


__all__ = ["python_execute", "PythonExecutionResult"]
