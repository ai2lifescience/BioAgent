"""Context passed to existing deterministic workflows by SDK function tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .action_executor import ActionExecutor


@dataclass
class WorkflowContext:
    workflow_name: str
    allowed_actions: tuple[str, ...]
    action_executor: ActionExecutor
    user_context: dict[str, Any] | None = None
    log_fn: Callable[[str], None] | None = None
    action_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self.action_calls

    @property
    def run_id(self) -> str | None:
        return str((self.user_context or {}).get("run_id") or "") or None

    @property
    def runtime_dir(self) -> str | None:
        return str((self.user_context or {}).get("runtime_dir") or "") or None

    @property
    def session_dir(self) -> str | None:
        return str((self.user_context or {}).get("session_dir") or "") or None

    @property
    def artifact_dir(self) -> str | None:
        return str((self.user_context or {}).get("artifact_dir") or "") or None

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        return [dict(x) for x in (self.user_context or {}).get("artifacts", []) if isinstance(x, dict)]

    def runtime_path(self, *parts: str) -> str:
        return str(Path(self.runtime_dir or "runtime").joinpath(*parts))

    def artifact_path(self, *parts: str) -> str:
        return str(Path(self.artifact_dir or self.runtime_path("artifacts")).joinpath(*parts))

    def latest_artifact(self, kinds: tuple[str, ...] = (), suffixes: tuple[str, ...] = ()) -> dict[str, Any] | None:
        suffixes = tuple(x.lower() for x in suffixes)
        for artifact in reversed(self.artifacts):
            path = str(artifact.get("path") or "")
            if kinds and artifact.get("kind") not in kinds:
                continue
            if suffixes and not path.lower().endswith(suffixes):
                continue
            return artifact
        return None

    def run_action(self, action: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self._log(f"[action] Started {action}.")
        record = self.action_executor.execute(
            workflow=self.workflow_name,
            action=action,
            arguments=arguments,
            allowed_actions=self.allowed_actions,
            user_context=self.user_context,
        )
        self.action_calls.append(record)
        self._log(f"[action] Finished {action}.")
        return record

    # Existing workflows use this name; it is now a direct action call, not an agent loop.
    run_tool = run_action

    def _log(self, message: str) -> None:
        if self.log_fn:
            self.log_fn(message)


def ensure_workflow_context(context: WorkflowContext | None, workflow_name: str) -> WorkflowContext:
    if context is None:
        raise RuntimeError(f"Workflow {workflow_name} requires an Agents SDK run context.")
    if context.workflow_name != workflow_name:
        raise RuntimeError(f"Context for {context.workflow_name} cannot run {workflow_name}.")
    return context
