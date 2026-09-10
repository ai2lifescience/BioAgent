"""Structured user-clarification tool implementation."""

from __future__ import annotations

from typing import Any


def ask_user_tool(
    question: str,
    options: list[str],
    other_label: str = "Other",
) -> dict[str, Any]:
    """Return a validated question that the interface can present to the user."""
    normalized_question = " ".join(str(question).split())
    if not normalized_question:
        raise ValueError("question must not be empty.")

    normalized_other_label = " ".join(str(other_label).split()) or "Other"
    normalized_options: list[str] = []
    seen: set[str] = {normalized_other_label.casefold()}
    for option in options:
        normalized_option = " ".join(str(option).split())
        if not normalized_option:
            raise ValueError("options must not contain empty values.")
        if normalized_option.casefold() in seen:
            raise ValueError("options must be unique and must not include the other_label.")
        seen.add(normalized_option.casefold())
        normalized_options.append(normalized_option)

    if len(normalized_options) < 2:
        raise ValueError("at least two options are required.")
    if len(normalized_options) > 6:
        raise ValueError("at most six options are allowed.")

    return {
        "status": "awaiting_user_input",
        "needs_input": True,
        "question": normalized_question,
        "options": normalized_options,
        "other_label": normalized_other_label,
        "summary": "Waiting for the user to choose an option or provide another answer.",
    }
