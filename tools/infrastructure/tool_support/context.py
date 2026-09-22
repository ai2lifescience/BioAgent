"""Host-side context passed to one SDK FunctionTool operation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationContext:
    """Internal metadata; model-facing schemas contain no host paths."""

    operation_name: str
    user_context: dict[str, Any] | None = None

    @property
    def session_dir(self) -> str | None:
        return str((self.user_context or {}).get("session_dir") or "") or None

    @property
    def workspace_dir(self) -> str | None:
        return str((self.user_context or {}).get("workspace_dir") or "") or None

    @property
    def files(self) -> list[dict[str, Any]]:
        return [dict(item) for item in (self.user_context or {}).get("files", []) if isinstance(item, dict)]
