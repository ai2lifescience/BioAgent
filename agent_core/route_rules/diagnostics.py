"""Diagnostic and example-skill route rules."""

from __future__ import annotations

import re
from typing import Any

from agent_core.router import IntentRoute

from .common import extract_labeled_value


def route_example_skill(user_request: str) -> IntentRoute | None:
    if not re.search(
        r"\b(example skill|demo skill|demo tool|test skill calling|example_skill)\b",
        user_request,
        flags=re.IGNORECASE,
    ):
        return None

    message = extract_labeled_value(user_request, "message")
    tag = extract_labeled_value(user_request, "tag")
    uppercase = bool(re.search(r"\buppercase\b", user_request, flags=re.IGNORECASE))
    if not message:
        message = user_request
    args: dict[str, Any] = {"message": message, "uppercase": uppercase}
    if tag:
        args["tag"] = tag
    return IntentRoute(
        mode="direct_skill",
        skill_name="example_skill",
        arguments=args,
        reason="Matched an explicit example skill test request.",
    )
