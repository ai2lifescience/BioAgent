"""Diagnostic tool implementations."""

from __future__ import annotations

from typing import Any


def echo_tool(
    message: str,
    tag: str | None = None,
    uppercase: bool = False,
) -> dict[str, Any]:
    normalized_message = " ".join(str(message).split())
    if not normalized_message:
        raise ValueError("message must not be empty.")
    echoed_message = normalized_message.upper() if uppercase else normalized_message
    return {
        "status": "ok",
        "tag": tag or "example",
        "echo": echoed_message,
        "input_length": len(str(message)),
        "normalized_length": len(normalized_message),
        "word_count": len(normalized_message.split()),
    }
