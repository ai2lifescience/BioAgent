"""Workflow for requesting missing information from the user."""

from __future__ import annotations

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Ask the user one focused clarifying question when a required detail "
            "or preference is genuinely unknown and work cannot continue. Provide "
            "two to six concrete choices; the UI always offers a free-text Other "
            "response. Do not use for information that can be obtained from a "
            "registered skill or for nonessential preferences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A concise question explaining the missing detail.",
                },
                "options": {
                    "type": "array",
                    "description": "Two to six mutually exclusive choices. Do not include Other.",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 6,
                },
                "other_label": {
                    "type": "string",
                    "description": "Optional label for the free-text response.",
                    "default": "Other",
                },
            },
            "required": ["question", "options"],
            "additionalProperties": False,
        },
    },
}


def ask_user(
    question: str,
    options: list[str],
    other_label: str = "Other",
    context: SkillContext | None = None,
) -> dict[str, object]:
    """Request user input and return without attempting further work."""
    context = ensure_skill_context(context, "ask_user")
    result = context.run_tool(
        "ask_user",
        {
            "question": question,
            "options": options,
            "other_label": other_label,
        },
    )["result"]
    return {"tool": "ask_user", **result}
