"""Public JSON contracts shared by runtime, HTTP, and browser clients.

The workspace inventory and files produced by one run are deliberately separate.
Keeping both under a generic ``files`` key made it too easy for a client to
render an old workspace artifact on an unrelated answer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RunStatus = Literal["ok", "error", "blocked", "pending_approval"]


class PublicRunResult(BaseModel):
    """Stable envelope returned by direct and streamed agent runs.

    Extra fields remain allowed so runtime-specific metadata can evolve without
    breaking older clients. The named fields form the cross-interface contract.
    """

    model_config = ConfigDict(extra="allow")

    result_contract_version: Literal[1] = 1
    answer: str = ""
    status: RunStatus = "ok"
    session_id: str = ""
    approval_required: bool = False
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    workspace_files: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    # Compatibility alias retained for callers written before contract v1.
    files: list[dict[str, Any]] = Field(default_factory=list)


def normalize_run_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a public result without leaking host paths."""

    value = dict(payload)
    workspace_files = value.get("workspace_files")
    if not isinstance(workspace_files, list):
        workspace_files = value.get("files") if isinstance(value.get("files"), list) else []
    value["workspace_files"] = workspace_files
    # ``files`` stays an alias for one release cycle so older UI clients keep
    # working while new clients use the explicit name.
    value["files"] = workspace_files
    if not isinstance(value.get("artifacts"), list):
        value["artifacts"] = []
    return PublicRunResult.model_validate(value).model_dump(mode="json")


__all__ = ["PublicRunResult", "RunStatus", "normalize_run_result"]
