"""Workspace path helpers for SDK sandbox-aware FunctionTools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.infrastructure.tool_support.context import WorkflowContext


def session_root(context: WorkflowContext) -> Path:
    """Return the active session root, creating it for workspace writes."""
    if not context.session_dir:
        raise ValueError("The active session does not have a workspace root.")
    root = Path(context.session_dir)
    if root.is_symlink():
        raise ValueError("Workspace roots cannot be symbolic links.")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_session_path(context: WorkflowContext, value: str) -> Path:
    """Resolve a safe relative path inside the active session workspace."""
    candidate = Path(str(value))
    if candidate.is_absolute() or ".." in candidate.parts or any(part.startswith(".") for part in candidate.parts):
        raise ValueError("Workspace paths must be relative and cannot access hidden or parent directories.")
    root = session_root(context)
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Workspace paths must stay inside the active session.")
    return resolved


def resolve_workspace_item(context: WorkflowContext, item: dict[str, Any]) -> tuple[Path, str]:
    """Resolve one file-list item and return its host path and public path."""
    public_path = str(item.get("workspace_path") or item.get("path") or "")
    relative = str(item.get("workspace_path") or "").strip()
    if relative and context.session_dir:
        root = session_root(context)
        resolved = (root / relative).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("Workspace paths must stay inside the active session.")
    else:
        raw = str(item.get("path") or "").strip()
        resolved = Path(raw).expanduser().resolve() if raw else Path()
    if not resolved.is_file():
        raise FileNotFoundError(f"Workspace file is not available: {public_path}")
    return resolved, public_path


def select_workspace_file(context: WorkflowContext, requested: str | None = None,
                          *, suffixes: tuple[str, ...] = ()) -> tuple[Path, str]:
    """Resolve a listed session file and return its host path plus public path."""
    candidates = context.files
    requested = str(requested or "").strip()
    if requested:
        matches = [
            item for item in candidates
            if requested in {
                str(item.get("workspace_path") or ""),
                str(item.get("path") or ""),
                str(item.get("name") or ""),
            }
        ]
    else:
        matches = list(candidates)
    if suffixes:
        normalized = tuple(value.lower() for value in suffixes)
        matches = [
            item for item in matches
            if str(item.get("workspace_path") or item.get("path") or "").lower().endswith(normalized)
        ]
    if not matches:
        label = f" matching {requested!r}" if requested else ""
        raise ValueError(f"No workspace file is available{label}.")

    item = max(matches, key=lambda value: int(value.get("modified_at") or 0))
    return resolve_workspace_item(context, item)


def workspace_output_path(context: WorkflowContext, *parts: str) -> Path:
    """Create a path under the run output directory, without accepting traversal."""
    root = _output_root(context)
    candidate = confined_output_path(root, *parts)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def workspace_output_dir(
    context: WorkflowContext,
    requested: str | Path | None = None,
    *default_parts: str,
) -> Path:
    """Resolve a tool output directory inside the active session workspace.

    Relative caller paths are workspace-relative. Absolute paths are accepted
    only when they already point inside the active session; symlink resolution
    happens before the containment check so a link cannot escape the workspace.
    """
    output_root = _output_root(context)
    candidate = (
        confined_output_path(output_root, *default_parts)
        if requested in (None, "")
        else confined_output_path(output_root, str(requested))
    )
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def session_output_dir(
    context: WorkflowContext,
    requested: str | Path | None = None,
    *default_parts: str,
) -> Path:
    """Resolve an internal cache directory anywhere inside the session root."""
    root = session_root(context)
    candidate = (
        confined_output_path(root, *default_parts)
        if requested in (None, "")
        else confined_output_path(root, str(requested))
    )
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _output_root(context: WorkflowContext) -> Path:
    root = session_root(context)
    # workspace_dir is host-owned run metadata, never a model-supplied base.
    if context.workspace_dir:
        raw = Path(context.workspace_dir)
        configured = (raw if raw.is_absolute() else root / raw).resolve()
    else:
        configured = root / "outputs"
    return confined_output_path(root, str(configured))


def confined_output_path(root: Path, *parts: str) -> Path:
    """Validate a destination, including existing directory and file symlinks.

    Low-level writers use this with an output directory already validated by
    the workflow. This checks the actual filename, not only its parent folder.
    """
    root = root.resolve()
    if any(".." in Path(part).parts for part in parts):
        raise ValueError("Output paths cannot contain parent-directory traversal.")
    candidate = root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Output paths must stay inside the active workspace directory.")
    return candidate


def output_file_path(directory: str | Path, filename: str) -> Path:
    """Validate a single output filename under a workflow-selected directory."""
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ValueError("Output filenames must be plain names, without directory components.")
    return confined_output_path(Path(directory), filename)


__all__ = [
    "confined_output_path",
    "output_file_path",
    "resolve_session_path",
    "resolve_workspace_item",
    "session_output_dir",
    "select_workspace_file",
    "session_root",
    "workspace_output_dir",
    "workspace_output_path",
]
