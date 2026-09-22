"""Typed result contracts shared by SDK FunctionTools."""
from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from agents import RunContextWrapper
from pydantic import BaseModel, ConfigDict, Field


class FunctionContract(BaseModel):
    """Strict JSON model used at the model-facing tool boundary."""

    model_config = ConfigDict(extra="forbid")


class FunctionArtifact(FunctionContract):
    path: str
    workspace_path: str
    name: str
    kind: str
    content_type: str
    size: int
    modified_at: int


_FunctionData = TypeVar("_FunctionData")


class ToolError(FunctionContract):
    code: str
    message: str


class FunctionResult(FunctionContract, Generic[_FunctionData]):
    """One stable envelope for successful, failed, and blocked operations."""

    status: Literal["ok", "error", "blocked"] = "ok"
    data: _FunctionData
    files: list[FunctionArtifact] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    error: ToolError | None = None

    def __str__(self) -> str:
        return self.model_dump_json()


def tool_error(ctx: RunContextWrapper[Any], error: Exception) -> str:
    """Format SDK validation/invocation failures using the same result envelope."""
    context = ctx.context
    name = getattr(ctx, "tool_name", "unknown_tool")
    payload = FunctionResult[dict[str, Any]](
        status="error",
        data={},
        error=ToolError(code=type(error).__name__, message=str(error)),
    )
    public = context.public(payload.model_dump(mode="json")) if hasattr(context, "public") else payload.model_dump(mode="json")
    if hasattr(context, "tool_results"):
        context.tool_results.append({
            "tool": name,
            "arguments": {},
            "result": {},
            "status": "error",
            "error": public["error"]["message"],
            "error_type": public["error"]["code"],
            "tool_calls": [],
        })
        context.record("tool_failed", tool=name, error_type=type(error).__name__)
    return FunctionResult[dict[str, Any]].model_validate(public).model_dump_json()
