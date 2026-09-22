"""Workspace-relative artifact adapters used by SDK FunctionTools.

Only this infrastructure module deals with host-side paths. Public tool
contracts expose paths relative to the current session workspace.
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from tools.infrastructure.workspace import resolve_session_path, workspace_output_path, session_root
from tools.infrastructure.workspace.artifacts import workspace_file_metadata
from .evidence_models import EvidenceArtifact, EvidenceRecord


def input_path(context, path: str, suffixes: tuple[str, ...] = (), max_bytes: int = 32 * 1024 * 1024) -> Path:
    source = resolve_session_path(context, path)
    if not source.is_file():
        raise ValueError(f"Workspace file does not exist: {path}")
    if suffixes and source.suffix.lower() not in suffixes:
        raise ValueError(f"File must use one of: {', '.join(suffixes)}")
    if source.stat().st_size > max_bytes:
        raise ValueError(f"File exceeds the {max_bytes} byte limit.")
    return source


def load_evidence(
    context,
    paths: list[str],
    *,
    max_file_bytes: int = 4 * 1024 * 1024,
    max_total_bytes: int = 8 * 1024 * 1024,
) -> list[EvidenceRecord]:
    """Load and deduplicate versioned evidence artifacts from workspace paths."""
    unique: dict[str, EvidenceRecord] = {}
    total_bytes = 0
    for path in paths:
        source = input_path(context, path, (".json",), max_bytes=max_file_bytes)
        total_bytes += source.stat().st_size
        if total_bytes > max_total_bytes:
            raise ValueError(f"Evidence inputs exceed the {max_total_bytes} byte limit.")
        try:
            artifact = EvidenceArtifact.model_validate(json.loads(source.read_text(encoding="utf-8")))
        except ValueError as exc:
            raise ValueError("Expected an evidence artifact returned by a search or retrieval tool.") from exc
        for record in artifact.sources:
            unique[record.id] = record
    return list(unique.values())


def destination(context, filename: str) -> Path:
    return workspace_output_path(context, context.operation_name, uuid4().hex, filename)


def artifact(context, path: Path) -> dict:
    public = path.relative_to(session_root(context)).as_posix()
    return {
        "path": public,
        "workspace_path": public,
        "name": path.name,
        "size": path.stat().st_size,
        "modified_at": path.stat().st_mtime_ns,
        **workspace_file_metadata(path),
    }


def write_json(context, filename: str, value) -> dict:
    path = destination(context, filename)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return artifact(context, path)


def output(data: dict, *files: dict) -> dict:
    return {"status": "ok", "data": data, "files": list(files), "evidence": []}


__all__ = ["artifact", "destination", "input_path", "load_evidence", "output", "write_json"]
