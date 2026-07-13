"""File I/O route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute

from .common import extract_quoted_or_labeled_path


def route_file_inspection(user_request: str) -> IntentRoute | None:
    if not re.search(r"\b(inspect|read|summarize|summarise|verify)\b", user_request, re.IGNORECASE):
        return None
    path = extract_quoted_or_labeled_path(user_request)
    if not path:
        return None
    return IntentRoute(
        mode="direct_skill",
        skill_name="file_inspection",
        arguments={"path": path},
        reason="Matched a local file inspection request.",
    )
