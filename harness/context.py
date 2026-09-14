"""Context shared by Agents SDK tools during one BioAgent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .action_executor import ActionExecutor
from .workflow_context import WorkflowContext


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BioRunContext:
    """Small run context; the Agents SDK owns orchestration and sessions."""

    session: Any
    model_key: str
    artifact_store: Any = None
    log_fn: Callable[[str], None] | None = None
    skill_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    action_executor: ActionExecutor = field(default_factory=ActionExecutor)

    @property
    def session_id(self) -> str:
        return str(self.session.session_id)

    @property
    def run(self) -> dict[str, Any]:
        return dict(self.session.metadata.get("run") or {})

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.session.metadata.get("artifacts") or []]

    def user_context(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "artifacts": self.artifacts,
            **self.run,
        }

    def skill_context(self, skill_name: str, allowed_tools: tuple[str, ...]) -> WorkflowContext:
        return WorkflowContext(
            workflow_name=skill_name,
            allowed_actions=allowed_tools,
            action_executor=self.action_executor,
            user_context=self.user_context(),
            log_fn=self.log,
        )

    def record(self, event: str, **data: Any) -> None:
        item = {"timestamp": _now(), "session_id": self.session_id, "event": event, "data": data}
        self.events.append(item)
        if self.log_fn and event in {"tool_started", "tool_finished", "agent_started", "agent_finished"}:
            message = data.get("message") or event.replace("_", " ").capitalize()
            self.log_fn(f"[agents] {message}")

    def log(self, message: str) -> None:
        if self.log_fn:
            self.log_fn(message)
