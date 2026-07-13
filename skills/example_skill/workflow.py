"""Example skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "example_skill",
        "description": (
            "Run a local diagnostic workflow that calls the echo tool and returns "
            "structured metadata. Use when the user asks to test skill calling, "
            "verify tool calling, run a demo skill, or check the registry."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo."},
                "tag": {"type": "string", "description": "Optional test label.", "default": "example"},
                "uppercase": {
                    "type": "boolean",
                    "description": "Whether to uppercase the echoed message.",
                    "default": False,
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
}


def example_skill(
    message: str,
    tag: str | None = None,
    uppercase: bool = False,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "example_skill")
    result = context.run_tool(
        "echo",
        {"message": message, "tag": tag, "uppercase": uppercase}
    )["result"]
    answer = (
        "Example skill completed.\n"
        f"Status: {result.get('status', 'unknown')}\n"
        f"Tag: {result.get('tag', 'example')}\n"
        f"Echo: {result.get('echo', '')}\n"
        f"Word count: {result.get('word_count', 0)}"
    )
    return {"skill": "example_skill", "tool": "echo", "answer": answer, **result}
