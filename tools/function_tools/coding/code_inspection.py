"""Read-only workspace code inspection."""
from __future__ import annotations

from typing import Any, Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


import hashlib
import os
from pathlib import Path
from tools.infrastructure.tool_support.context import OperationContext
from tools.infrastructure.workspace import resolve_session_path, session_root
from tools.infrastructure.tool_support.artifacts import output

class Entry(FunctionContract):
    path: str
    bytes: int
    suffix: str


class Match(FunctionContract):
    path: str
    line: int
    excerpt: str


class InspectionResult(FunctionContract):
    operation: Literal["tree", "read", "search"]
    path: str | None = None
    entries: list[Entry] = Field(default_factory=list)
    content: str | None = None
    truncated: bool = False
    sha256: str | None = None
    query: str | None = None
    matches: list[Match] = Field(default_factory=list)
    matched_count: int = 0
    summary: str


MAX_READ_BYTES = 512 * 1024
IGNORED_NAMES = {".git", ".venv", "__pycache__", "node_modules", "runtime"}


def _operation(
    operation: str = "tree",
    path: str | None = None,
    query: str | None = None,
    max_matches: int = 50,
    max_chars: int = 50_000,
    context: OperationContext | None = None,
) -> dict[str, Any]:
    root = session_root(context)
    operation = str(operation or "tree").strip().lower()
    if operation not in {"tree", "read", "search"}:
        raise ValueError("operation must be tree, read, or search.")
    if operation == "tree":
        target = resolve_session_path(context, path or ".")
        if not target.exists():
            raise FileNotFoundError(f"Workspace path is not available: {path}")
        entries = _tree(target, root, max_matches)
        return output({"operation": operation, "path": _public_path(target, root), "entries": entries, "summary": f"Listed {len(entries)} workspace path(s)."})
    if operation == "read":
        if not path:
            raise ValueError("read operation requires a workspace-relative path.")
        target = resolve_session_path(context, path)
        content = _read_text(target, max_chars)
        return output({"operation": operation, "path": _public_path(target, root), "content": content, "truncated": target.stat().st_size > max_chars, "sha256": _sha256(target), "summary": f"Read {_public_path(target, root)}."})
    if not query or len(query.strip()) < 2:
        raise ValueError("search operation requires a query of at least two characters.")
    matches = _search(root, query, min(max(int(max_matches), 1), 200), max_chars)
    return output({"operation": operation, "query": query, "matches": matches, "matched_count": len(matches), "summary": f"Found {len(matches)} code match(es)."})

def _public_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path != root else "."

def _iter_files(root: Path):
    for current, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in IGNORED_NAMES and not name.startswith(".") and not (Path(current) / name).is_symlink())
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(current) / name
            if not path.is_symlink() and path.is_file():
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

@bio_function_tool()
async def code_inspection(
    ctx: RunContextWrapper[AgentRunContext],
    operation: Annotated[Literal["tree", "read", "search"], Field(description="Read-only workspace inspection operation.")],
    path: Annotated[str | None, Field(description="Workspace-relative path for tree or read.")] = None,
    query: Annotated[str | None, Field(description="Text to find when operation is search.")] = None,
    max_matches: Annotated[int, Field(ge=1, le=200)] = 50,
    max_chars: Annotated[int, Field(ge=100, le=50000)] = 50000,
) -> FunctionResult[InspectionResult]:
    """Inspect, read, or search workspace code without changing files."""
    return await invoke(ctx.context, "code_inspection", _operation,
                              {"operation": operation, "path": path, "query": query,
                               "max_matches": max_matches, "max_chars": max_chars}, FunctionResult[InspectionResult])


__all__ = ["code_inspection"]
