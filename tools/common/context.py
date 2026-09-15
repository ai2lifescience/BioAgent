"""Application dependencies and evidence capture for deterministic workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class WorkflowContext:
    workflow_name: str
    user_context: dict[str, Any] | None = None
    log_fn: Callable[[str], None] | None = None
    action_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self.action_calls

    @property
    def run_id(self) -> str | None:
        return str((self.user_context or {}).get('run_id') or '') or None

    @property
    def runtime_dir(self) -> str | None:
        return str((self.user_context or {}).get('runtime_dir') or '') or None

    @property
    def session_dir(self) -> str | None:
        return str((self.user_context or {}).get('session_dir') or '') or None

    @property
    def workspace_dir(self) -> str | None:
        return str((self.user_context or {}).get('workspace_dir') or '') or None

    @property
    def files(self) -> list[dict[str, Any]]:
        return [dict(x) for x in (self.user_context or {}).get('files', []) if isinstance(x, dict)]

    def runtime_path(self, *parts: str) -> str:
        return str(Path(self.runtime_dir or 'runtime').joinpath(*parts))

    def workspace_path(self, *parts: str) -> str:
        return str(Path(self.workspace_dir or self.runtime_path('outputs')).joinpath(*parts))

    def latest_file(self, kinds: tuple[str, ...] = (), suffixes: tuple[str, ...] = ()) -> dict[str, Any] | None:
        suffixes = tuple(x.lower() for x in suffixes)
        for artifact in reversed(self.files):
            path = str(artifact.get('path') or '')
            if kinds and artifact.get('kind') not in kinds and artifact.get('kind') != 'upload':
                continue
            if suffixes and not path.lower().endswith(suffixes):
                continue
            return artifact
        return None

    def call(self, name: str, handler: Callable[..., Any], arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an explicitly imported Python function and retain its evidence.

        This is instrumentation, not a tool-name dispatcher. The model cannot
        select the callable or bypass the public FunctionTool's validation.
        """
        if self.log_fn:
            self.log_fn(f'[action] Started {name}.')
        record = {'skill': self.workflow_name, 'tool': name, 'arguments': arguments}
        try:
            value = handler(**arguments)
            result = value if isinstance(value, dict) else {'value': value}
            record.update(result=result, status='error' if result.get('error') or result.get('status') == 'error' else 'ok', error=result.get('error'))
            return record
        except Exception as exc:
            record.update(result={'error': str(exc), 'error_type': type(exc).__name__}, status='error', error=str(exc))
            raise
        finally:
            self.action_calls.append(record)
            if self.log_fn:
                self.log_fn(f'[action] Finished {name}: {record["status"]}.')


def ensure_workflow_context(context: WorkflowContext | None, workflow_name: str) -> WorkflowContext:
    if context is None or context.workflow_name != workflow_name:
        raise RuntimeError(f'Workflow {workflow_name} requires its run context.')
    return context
