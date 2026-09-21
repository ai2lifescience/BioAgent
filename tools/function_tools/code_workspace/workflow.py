"""Read-only inspection, edits, and bounded test commands in a session."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from tools.infrastructure.tool_support.context import WorkflowContext, ensure_workflow_context
from tools.infrastructure.workspace import resolve_session_path, session_root


MAX_READ_BYTES = 512 * 1024
MAX_EDIT_BYTES = 1 * 1024 * 1024
IGNORED_NAMES = {".git", ".venv", "__pycache__", "node_modules", "runtime"}


def code_inspection(
    operation: str = "tree",
    path: str | None = None,
    query: str | None = None,
    max_matches: int = 50,
    max_chars: int = 50_000,
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "code_inspection")
    root = _root(context)
    operation = str(operation or "tree").strip().lower()
    if operation not in {"tree", "read", "search"}:
        raise ValueError("operation must be tree, read, or search.")
    if operation == "tree":
        target = resolve_session_path(context, path or ".")
        if not target.exists():
            raise FileNotFoundError(f"Workspace path is not available: {path}")
        entries = _tree(target, root, max_matches)
        return {"status": "ok", "operation": operation, "path": _public_path(target, root), "entries": entries, "summary": f"Listed {len(entries)} workspace path(s)."}
    if operation == "read":
        if not path:
            raise ValueError("read operation requires a workspace-relative path.")
        target = resolve_session_path(context, path)
        content = _read_text(target, max_chars)
        return {"status": "ok", "operation": operation, "path": _public_path(target, root), "content": content, "truncated": target.stat().st_size > max_chars, "sha256": _sha256(target), "summary": f"Read {_public_path(target, root)}."}
    if not query or len(query.strip()) < 2:
        raise ValueError("search operation requires a query of at least two characters.")
    matches = _search(root, query, min(max(int(max_matches), 1), 200), max_chars)
    return {"status": "ok", "operation": operation, "query": query, "matches": matches, "matched_count": len(matches), "summary": f"Found {len(matches)} code match(es)."}


def code_edit(
    path: str,
    content: str,
    expected_sha256: str | None = None,
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "code_edit")
    root = _root(context)
    target = resolve_session_path(context, path)
    if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
        raise ValueError("Edited files are limited to 1 MB.")
    if target.exists() and target.is_dir():
        raise ValueError("The edit path is a directory.")
    if target.exists() and expected_sha256 and _sha256(target) != expected_sha256:
        raise ValueError("The file changed since inspection; refresh it before editing.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, target)
    return {"status": "ok", "changed_files": [_public_path(target, root)], "path": _public_path(target, root), "sha256": _sha256(target), "bytes": target.stat().st_size, "summary": f"Updated {_public_path(target, root)}."}


def code_test(
    command: str = "python -m compileall .",
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "code_test")
    allowed = {"python -m pytest", "python -m unittest", "python -m compileall ."}
    if command not in allowed:
        raise ValueError("command must be one of: python -m pytest, python -m unittest, python -m compileall .")
    root = _root(context)
    completed = subprocess.run(
        command.split(), cwd=root, capture_output=True, text=True, timeout=120,
        env={key: value for key, value in os.environ.items() if key not in {"OPENAI_API_KEY", "OPENROUTER_API_KEY"}},
    )
    output = (completed.stdout + ("\n" + completed.stderr if completed.stderr else "")).strip()
    return {"status": "ok" if completed.returncode == 0 else "error", "command": command, "returncode": completed.returncode, "test_result": "passed" if completed.returncode == 0 else "failed", "logs": output[-20_000:], "summary": f"{command} {'passed' if completed.returncode == 0 else 'failed'} with exit code {completed.returncode}."}


def _root(context: WorkflowContext) -> Path:
    return session_root(context)


def _public_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path != root else "."


def _iter_files(root: Path):
    for current, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in IGNORED_NAMES and not name.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(current) / name
            if path.is_file():
                yield path


def _tree(target: Path, root: Path, limit: int) -> list[dict[str, Any]]:
    paths = [target] if target.is_file() else list(_iter_files(target))
    entries = []
    for path in paths[:limit]:
        entries.append({"path": _public_path(path, root), "bytes": path.stat().st_size, "suffix": path.suffix.lower()})
    return entries


def _read_text(path: Path, max_chars: int) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Workspace file is not available: {path.name}")
    if path.stat().st_size > MAX_READ_BYTES:
        raise ValueError("The file is too large for bounded inspection.")
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except UnicodeDecodeError as exc:
        raise ValueError("The selected file is not a readable text file.") from exc


def _search(root: Path, query: str, limit: int, max_chars: int) -> list[dict[str, Any]]:
    matches = []
    needle = query.lower()
    for path in _iter_files(root):
        if path.stat().st_size > MAX_READ_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line, value in enumerate(text.splitlines(), 1):
            if needle in value.lower():
                matches.append({"path": _public_path(path, root), "line": line, "excerpt": value[:max_chars]})
                if len(matches) >= limit:
                    return matches
    return matches


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["code_inspection", "code_edit", "code_test"]
