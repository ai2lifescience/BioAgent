"""Base tool objects for concrete agent actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolDefinition:
    """A concrete callable action with policy metadata."""

    name: str
    description: str
    handler: Callable[..., dict[str, Any]]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    risk_level: str = "low"
    requires_confirmation: bool = False
    auth_required: bool = False

    def run(
        self,
        input_data: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the tool after simple permission and input checks."""
        payload = dict(input_data or {})
        if self.auth_required and not (user_context or {}).get("authenticated"):
            raise PermissionError(f"Tool {self.name} requires authenticated user context.")
        if self.requires_confirmation and not (user_context or {}).get("confirmed"):
            raise PermissionError(f"Tool {self.name} requires explicit confirmation.")
        return self.handler(**payload)
