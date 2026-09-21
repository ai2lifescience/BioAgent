"""Context shared by Agents SDK tools during one Pipeline2Agent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from tools.infrastructure.tool_support.context import WorkflowContext


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentRunContext:
    """Small run context; the Agents SDK owns orchestration and sessions."""

    session: Any
    model_key: str
    sandbox_session: Any = None
    log_fn: Callable[[str], None] | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)

    @property
    def session_id(self) -> str:
        return str(self.session.session_id)

    @property
    def run(self) -> dict[str, Any]:
        return dict(self.session.metadata.get("run") or {})

    def user_context(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "files": [dict(item) for item in self.files],
            "_agent_context": self,
            **self.run,
        }

    def workflow_context(self, workflow_name: str) -> WorkflowContext:
        return WorkflowContext(
            workflow_name=workflow_name,
            user_context=self.user_context(),
            log_fn=self.log,
        )

    def public(self, value: Any) -> Any:
        from tools.infrastructure.workspace.public import public_payload
        return public_payload(value, self.run.get("session_dir"))

    def record(self, event: str, **data: Any) -> None:
        data = self.public(data)
        item = {"timestamp": _now(), "session_id": self.session_id, "event": event, "data": data}
        self.events.append(item)
        if self.log_fn and event in {"tool_started", "tool_finished", "agent_started", "agent_finished"}:
            message = data.get("message") or event.replace("_", " ").capitalize()
            self.log_fn(f"[agents] {message}")

    def log(self, message: str) -> None:
        if self.log_fn:
            self.log_fn(self.public(message))
