"""Routing for explicit requests to review completed pipeline outputs."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute


def _pipeline_name(user_request: str) -> str:
    labeled = re.search(
        r"\bpipeline[_ -]?name\b\s*(?::|=)?\s*(['\"]?)([A-Za-z0-9_.-]+)\1",
        user_request,
        flags=re.IGNORECASE,
    )
    if labeled:
        return labeled.group(2).strip(" .,:;")
    contextual = re.search(
        r"\bfrom\s+(?:the\s+)?([A-Za-z0-9_.-]+)\s+pipeline\b",
        user_request,
        flags=re.IGNORECASE,
    )
    if not contextual:
        return ""
    value = contextual.group(1).strip(" .,:;")
    return "" if value.lower() in {"this", "latest", "last"} else value


def route_pipeline_results(user_request: str) -> IntentRoute | None:
    has_action = re.search(
        r"\b(collect|show|review|summari[sz]e|display|interpret)\b",
        user_request,
        flags=re.IGNORECASE,
    )
    has_pipeline_results = re.search(
        r"\b(?:pipeline\s+(?:run\s+)?results?|results?\b.*\bpipeline(?:\s+run)?)\b",
        user_request,
        flags=re.IGNORECASE,
    )
    if not has_action or not has_pipeline_results:
        return None
    arguments = {}
    pipeline_name = _pipeline_name(user_request)
    if pipeline_name:
        arguments["pipeline_name"] = pipeline_name
    return IntentRoute(
        mode="direct_skill",
        skill_name="pipeline_results",
        arguments=arguments,
        reason="Matched an explicit request to collect and display completed pipeline results.",
    )
