"""NCBI retrieval route rule."""

from __future__ import annotations

from bio_data.ncbi import build_ncbi_args_from_text_request

from agent_core.router import IntentRoute


def route_ncbi(user_request: str) -> IntentRoute | None:
    args = build_ncbi_args_from_text_request(user_request)
    if args is None:
        return None
    return IntentRoute(
        mode="direct_skill",
        skill_name="ncbi_retrieval",
        arguments=args,
        reason="Matched a simple NCBI download/search request.",
    )
