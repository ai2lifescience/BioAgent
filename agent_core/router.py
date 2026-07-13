"""Intent routing for BioAgent."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IntentRoute:
    """A routing decision for one request."""

    mode: str
    skill_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "skill_name": self.skill_name,
            "arguments": self.arguments,
            "reason": self.reason,
        }


RouteRule = Callable[[str], IntentRoute | None]


class IntentRouter:
    """Route requests before the orchestrator asks the LLM fallback."""

    def __init__(self, rules: Iterable[RouteRule] | None = None) -> None:
        if rules is None:
            from .route_rules import ROUTE_RULES

            rules = ROUTE_RULES
        self.rules = tuple(rules)

    def route(self, user_request: str) -> IntentRoute:
        for rule in self.rules:
            route = rule(user_request)
            if route is not None:
                return route

        return IntentRoute(
            mode="llm_skill_loop",
            reason="No deterministic route matched.",
        )


__all__ = ["IntentRoute", "IntentRouter", "RouteRule"]
