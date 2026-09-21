"""Workspace coding tools with explicit approval for writes and tests."""

from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tooling.results import run_workflow
from tools.infrastructure.tooling.tooling import bio_function_tool

from .workflow import code_edit as _edit_workflow
from .workflow import code_inspection as _inspection_workflow
from .workflow import code_test as _test_workflow


@bio_function_tool()
async def code_inspection(
    ctx: RunContextWrapper[AgentRunContext],
    operation: Annotated[Literal["tree", "read", "search"], Field(description="Read-only workspace inspection operation.")],
    path: Annotated[str | None, Field(description="Workspace-relative path for tree or read.")] = None,
    query: Annotated[str | None, Field(description="Text to find when operation is search.")] = None,
    max_matches: Annotated[int, Field(ge=1, le=200)] = 50,
    max_chars: Annotated[int, Field(ge=100, le=50000)] = 50000,
) -> str:
    """Inspect, read, or search workspace code without changing files."""
    return await run_workflow(
        ctx.context, "code_inspection", _inspection_workflow,
        {"operation": operation, "path": path, "query": query, "max_matches": max_matches, "max_chars": max_chars},
        category="coding", with_progress=False,
    )


@bio_function_tool(needs_approval=True)
async def code_edit(
    ctx: RunContextWrapper[AgentRunContext],
    path: Annotated[str, Field(description="Workspace-relative file to create or replace.")],
    content: Annotated[str, Field(max_length=1000000, description="Complete replacement text for the file.")],
    expected_sha256: Annotated[str | None, Field(description="Optional hash from a prior read to prevent stale edits.")] = None,
) -> str:
    """Replace one workspace file after the user approves the exact content."""
    return await run_workflow(
        ctx.context, "code_edit", _edit_workflow,
        {"path": path, "content": content, "expected_sha256": expected_sha256},
        category="coding", with_progress=False,
    )


@bio_function_tool(timeout=180, needs_approval=True)
async def code_test(
    ctx: RunContextWrapper[AgentRunContext],
    command: Annotated[Literal["python -m pytest", "python -m unittest", "python -m compileall ."], Field(description="Bounded test command.")] = "python -m compileall .",
) -> str:
    """Run one approved, bounded test command in the workspace."""
    return await run_workflow(
        ctx.context, "code_test", _test_workflow, {"command": command}, category="coding", with_progress=False,
    )


__all__ = ["code_inspection", "code_edit", "code_test"]
