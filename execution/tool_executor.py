"""Controlled execution boundary for concrete tools."""

from __future__ import annotations

from typing import Any

from registries.tool_registry import get_tool


class ToolExecutor:
    """Run registered tools for a skill with lightweight architecture checks."""

    def execute_tool(
        self,
        skill_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        allowed_tools: tuple[str, ...] = (),
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(arguments or {})
        if allowed_tools and tool_name not in allowed_tools:
            allowed = ", ".join(sorted(allowed_tools))
            return self._error_record(
                skill_name=skill_name,
                tool_name=tool_name,
                arguments=payload,
                error=(
                    f"Tool {tool_name} is not allowed for skill {skill_name}. "
                    f"Allowed tools: {allowed}"
                ),
                error_type="PermissionError",
            )

        try:
            tool = get_tool(tool_name)
        except Exception as exc:
            return self._error_record(
                skill_name=skill_name,
                tool_name=tool_name,
                arguments=payload,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        try:
            self._validate_required_inputs(tool_name, payload, tool.input_schema)
            result = tool.run(payload, user_context=user_context)
        except Exception as exc:
            return self._error_record(
                skill_name=skill_name,
                tool_name=tool_name,
                arguments=payload,
                error=str(exc),
                error_type=type(exc).__name__,
                category=tool.category,
                risk_level=tool.risk_level,
            )

        return {
            "skill": skill_name,
            "tool": tool_name,
            "arguments": payload,
            "status": "ok",
            "result": result,
            "error": None,
            "category": tool.category,
            "risk_level": tool.risk_level,
        }

    @staticmethod
    def _error_record(
        skill_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        error: str,
        error_type: str,
        category: str = "unknown",
        risk_level: str = "unknown",
    ) -> dict[str, Any]:
        return {
            "skill": skill_name,
            "tool": tool_name,
            "arguments": arguments,
            "status": "error",
            "result": None,
            "error": error,
            "error_type": error_type,
            "category": category,
            "risk_level": risk_level,
        }

    @staticmethod
    def _validate_required_inputs(
        tool_name: str,
        payload: dict[str, Any],
        input_schema: dict[str, Any],
    ) -> None:
        missing = [
            field
            for field in input_schema.get("required", [])
            if field not in payload or payload[field] is None
        ]
        if missing:
            fields = ", ".join(missing)
            raise ValueError(f"Tool {tool_name} missing required input(s): {fields}")
