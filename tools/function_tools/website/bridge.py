"""Small, typed SDK tools backed by the trusted website adapter."""
from __future__ import annotations
from typing import Any, Annotated
import json
from agents import RunContextWrapper
from pydantic import Field
from harness.context import AgentRunContext
from harness.sandbox import session_root
from harness.website import get_bridge
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult

class ContextResult(FunctionContract):
    revision: str = ""
    title: str = ""
    context: dict[str, Any] = {}

class TableResult(FunctionContract):
    resource_id: str
    title: str = ""
    columns: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    offset: int = 0
    total_rows: int | None = None
    revision: str = ""

class FigureResult(FunctionContract):
    resource_id: str
    title: str = ""
    description: str = ""
    model_config = {"extra": "allow"}

class ManualSearchResult(FunctionContract):
    version: str = ""
    sections: list[dict[str, Any]] = []

class ManualResult(FunctionContract):
    section_id: str = ""
    title: str = ""
    version: str = ""
    text: str = ""

class ActionResult(FunctionContract):
    message: str = ""
    revision: str = ""
    model_config = {"extra": "allow"}

class ImportResult(FunctionContract):
    path: str
    filename: str
    bytes: int

def _binding(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    binding = ctx.context.run.get("website_binding")
    if not isinstance(binding, dict):
        raise ValueError("This tool requires an active trusted website embedding.")
    return binding

async def _call(ctx, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return await get_bridge().request(_binding(ctx), run_id=str(ctx.context.run.get("run_id", "")), method=method, arguments=arguments)

@bio_function_tool(timeout=60)
async def website_context(ctx: RunContextWrapper[AgentRunContext]) -> FunctionResult[ContextResult]:
    """Read the current page snapshot from the embedding website."""
    value = await _call(ctx, "getPageContext", {})
    return FunctionResult[ContextResult](status="ok", data=ContextResult(revision=str(value.get("revision", "")), title=str(value.get("title", "")), context=value))

@bio_function_tool(timeout=60)
async def website_read_table(ctx: RunContextWrapper[AgentRunContext], resource_id: Annotated[str, Field(min_length=1, max_length=120)], offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0, limit: Annotated[int, Field(ge=1, le=200)] = 50) -> FunctionResult[TableResult]:
    """Read one bounded page of a registered website table."""
    return FunctionResult[TableResult](status="ok", data=TableResult.model_validate(await _call(ctx, "readTable", {"resource_id": resource_id, "offset": offset, "limit": limit})))

@bio_function_tool(timeout=60)
async def website_read_figure(ctx: RunContextWrapper[AgentRunContext], resource_id: Annotated[str, Field(min_length=1, max_length=120)]) -> FunctionResult[FigureResult]:
    """Read structured values and semantics for a registered website figure."""
    return FunctionResult[FigureResult](status="ok", data=FigureResult.model_validate(await _call(ctx, "readFigure", {"resource_id": resource_id})))

@bio_function_tool(timeout=60)
async def website_search_manual(ctx: RunContextWrapper[AgentRunContext], query: Annotated[str, Field(min_length=1, max_length=500)], limit: Annotated[int, Field(ge=1, le=20)] = 5) -> FunctionResult[ManualSearchResult]:
    """Search the embedding website's versioned user manual."""
    return FunctionResult[ManualSearchResult](status="ok", data=ManualSearchResult.model_validate(await _call(ctx, "searchManual", {"query": query, "limit": limit})))

@bio_function_tool(timeout=60)
async def website_read_manual(ctx: RunContextWrapper[AgentRunContext], section_id: Annotated[str, Field(min_length=1, max_length=200)]) -> FunctionResult[ManualResult]:
    """Read one versioned section of the embedding website manual."""
    return FunctionResult[ManualResult](status="ok", data=ManualResult.model_validate(await _call(ctx, "readManual", {"section_id": section_id})))

@bio_function_tool(timeout=60)
async def website_import_data(ctx: RunContextWrapper[AgentRunContext], resource_id: Annotated[str, Field(min_length=1, max_length=120)]) -> FunctionResult[ImportResult]:
    """Export a registered website resource into the session workspace."""
    value = await _call(ctx, "exportData", {"resource_id": resource_id})
    filename = str(value.get("filename") or f"{resource_id}.txt").replace("/", "_")[:120]
    content = value.get("content", "")
    if not isinstance(content, str) or len(content.encode()) > 512 * 1024:
        raise ValueError("website export must be UTF-8 text under 512 KiB")
    root = session_root(ctx.context.session_id)
    target = root / "inputs" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    relative = target.relative_to(root).as_posix()
    file = {"path": relative, "workspace_path": relative, "name": target.name, "kind": "file", "content_type": str(value.get("content_type") or "text/plain"), "size": target.stat().st_size, "modified_at": target.stat().st_mtime_ns}
    return FunctionResult[ImportResult](status="ok", data=ImportResult(path=relative, filename=filename, bytes=file["size"]), files=[file])

@bio_function_tool(timeout=60)
async def website_highlight(ctx: RunContextWrapper[AgentRunContext], element_id: Annotated[str, Field(min_length=1, max_length=120)], message: Annotated[str, Field(max_length=500)] = "") -> FunctionResult[ActionResult]:
    """Highlight a registered page element for the user."""
    return FunctionResult[ActionResult](status="ok", data=ActionResult.model_validate(await _call(ctx, "highlight", {"element_id": element_id, "message": message})))

@bio_function_tool(timeout=60)
async def website_navigate(ctx: RunContextWrapper[AgentRunContext], route_id: Annotated[str, Field(min_length=1, max_length=120)]) -> FunctionResult[ActionResult]:
    """Navigate to a registered route in the embedding website."""
    return FunctionResult[ActionResult](status="ok", data=ActionResult.model_validate(await _call(ctx, "navigate", {"route_id": route_id})))

@bio_function_tool(timeout=60)
async def website_action(ctx: RunContextWrapper[AgentRunContext], action_id: Annotated[str, Field(min_length=1, max_length=120)], arguments_json: Annotated[str, Field(max_length=8000)] = "{}") -> FunctionResult[ActionResult]:
    """Invoke a host-registered website action with a JSON object argument string."""
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        raise ValueError("arguments_json must be a JSON object") from exc
    if not isinstance(arguments, dict):
        raise ValueError("arguments_json must encode a JSON object")
    value = await _call(ctx, "invokeAction", {"action_id": action_id, "arguments": arguments})
    return FunctionResult[ActionResult](status="ok", data=ActionResult.model_validate(value))

WEBSITE_TOOLS = [website_context, website_read_table, website_read_figure, website_search_manual, website_read_manual, website_import_data, website_highlight, website_navigate, website_action]

__all__ = ["WEBSITE_TOOLS"]
