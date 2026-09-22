"""Run one bounded workspace test command."""
from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult



import asyncio
import os
import signal
import sys
from tools.infrastructure.workspace import session_root
from tools.infrastructure.tool_support.artifacts import output

class TestResult(FunctionContract):
    command: str
    returncode: int
    test_result: Literal["passed", "failed"]
    logs: str
    summary: str


async def _operation(*, command="python -m compileall .", context):
    if command not in {"python -m pytest", "python -m unittest", "python -m compileall ."}:
        raise ValueError("Unsupported test command.")
    process = await asyncio.create_subprocess_exec(
        sys.executable, *command.split()[1:], cwd=session_root(context),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env={key: value for key, value in os.environ.items()
             if key not in {"OPENAI_API_KEY", "OPENROUTER_API_KEY"}},
        start_new_session=True,
    )
    logs = bytearray()
    async def collect():
        while chunk := await process.stdout.read(8192):
            logs.extend(chunk)
            if len(logs) > 20_000:
                del logs[:-20_000]
        return await process.wait()
    try:
        returncode = await asyncio.wait_for(collect(), timeout=120)
    finally:
        # Stop descendants too, including on SDK cancellation or timeout.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
    state = "passed" if returncode == 0 else "failed"
    envelope = output({"command": command, "returncode": returncode, "test_result": state,
        "logs": logs.decode("utf-8", errors="replace").strip(),
        "summary": f"{command} {state} with exit code {returncode}."})
    if returncode:
        envelope.update(status="error", error={"code": "TEST_FAILED", "message": envelope["data"]["summary"]})
    return envelope


@bio_function_tool(timeout=180)
async def code_test(
    ctx: RunContextWrapper[AgentRunContext],
    command: Annotated[Literal["python -m pytest", "python -m unittest", "python -m compileall ."], "Bounded test command."] = "python -m compileall .",
) -> FunctionResult[TestResult]:
    """Run one allowlisted test command without SDK approval."""
    return await invoke(ctx.context, "code_test", _operation, {"command": command}, FunctionResult[TestResult])


__all__ = ["code_test"]
