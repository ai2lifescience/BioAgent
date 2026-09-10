"""Concrete definition for structured user clarification."""

from __future__ import annotations

from tools.ask_user.core import ask_user_tool
from tools.base import ToolDefinition


ASK_USER_TOOL = ToolDefinition(
    name="ask_user",
    description=(
        "Pause work to ask the user one focused clarifying question with "
        "selectable options and an Other response."
    ),
    handler=ask_user_tool,
    category="interaction",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The concise question the user must answer.",
            },
            "options": {
                "type": "array",
                "description": "Two to six mutually exclusive selectable answers; omit Other.",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 6,
            },
            "other_label": {
                "type": "string",
                "description": "Label for the free-text response option.",
                "default": "Other",
            },
        },
        "required": ["question", "options"],
        "additionalProperties": False,
    },
)
