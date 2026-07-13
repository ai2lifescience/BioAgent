"""Diagnostic concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.diagnostics.core import echo_tool


ECHO_TOOL = ToolDefinition(
    name="echo",
    description="Echo a message for skill/tool calling diagnostics.",
    handler=echo_tool,
    category="diagnostics",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "tag": {"type": "string", "default": "example"},
            "uppercase": {"type": "boolean", "default": False},
        },
        "required": ["message"],
    },
)
