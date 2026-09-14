"""Direct execution of deterministic biological actions for SDK tools."""

from __future__ import annotations

from typing import Any

from registries.tool_registry import get_tool


class ActionExecutor:
    """Keep validation and policy at the function-tool boundary."""

    def execute(
        self,
        workflow: str,
        action: str,
        arguments: dict[str, Any] | None = None,
        allowed_actions: tuple[str, ...] = (),
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(arguments or {})
        if allowed_actions and action not in allowed_actions:
            raise PermissionError(f"Action {action} is not allowed for workflow {workflow}.")
        tool = get_tool(action)
        missing = [key for key in tool.input_schema.get("required", []) if payload.get(key) is None]
        if missing:
            raise ValueError(f"Action {action} missing required input(s): {', '.join(missing)}")
        result = tool.run(payload, user_context=user_context)
        return {
            "skill": workflow,
            "tool": action,
            "workflow": workflow,
            "action": action,
            "arguments": payload,
            "result": result,
            "status": "ok",
            "error": None,
            "category": tool.category,
            "risk_level": tool.risk_level,
        }
