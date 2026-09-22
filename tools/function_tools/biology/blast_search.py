"""Submit a sequence to NCBI BLAST or poll an existing request."""
from __future__ import annotations

from typing import Any, Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from tools.infrastructure.providers.blast.client import run_blast_search
from tools.infrastructure.tool_support.artifacts import output

class BlastResult(FunctionContract):
    database: str
    program: str
    rid: str
    state: Literal["SUBMITTED", "READY", "TIMEOUT", "FAILED", "UNKNOWN"]
    estimated_seconds: int | None = None
    timeout_seconds: int | None = None
    format: str | None = None
    hit_count: int = 0
    hits: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None
    raw_status: str | None = None
    parse_error: str | None = None


def _operation(*, context, **arguments):
    result = run_blast_search(**arguments)
    result["state"] = result.pop("status")
    envelope = output(result)
    if result["state"] in {"FAILED", "UNKNOWN"} or result.get("parse_error"):
        envelope.update(status="error", error={"code": "BLAST_ERROR",
            "message": result.get("parse_error") or f"BLAST request {result['rid']} is {result['state']}."})
    return envelope


@bio_function_tool()
async def blast_search(
    ctx: RunContextWrapper[AgentRunContext],
    sequence: Annotated[str | None, Field(description="Sequence or FASTA text to submit. Provide rid instead to poll.")] = None,
    rid: Annotated[str | None, Field(description="Existing BLAST request ID to poll.")] = None,
    program: Literal["blastn", "blastp", "blastx", "tblastn", "tblastx"] = "blastn",
    database: str = "nt",
    hitlist_size: int = 10,
    expect: float = 10.0,
    wait: bool = False,
    timeout_seconds: int = 120,
) -> FunctionResult[BlastResult]:
    """Submit a similarity search or poll a BLAST request."""
    return await invoke(ctx.context, "blast_search", _operation,
                              {"sequence": sequence, "rid": rid, "program": program,
                               "database": database, "hitlist_size": hitlist_size,
                               "expect": expect, "wait": wait, "timeout_seconds": timeout_seconds}, FunctionResult[BlastResult])


__all__ = ["blast_search"]
