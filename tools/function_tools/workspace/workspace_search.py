"""Search text and selectable-PDF content in the active workspace."""
from __future__ import annotations

from typing import Any, Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from pathlib import Path
import re
from pypdf import PdfReader
from tools.infrastructure.tool_support.context import OperationContext
from tools.infrastructure.workspace import resolve_session_path, resolve_workspace_item
from tools.infrastructure.tool_support.artifacts import output

class Match(FunctionContract):
    path: str
    line: int | None = None
    page: int | None = None
    excerpt: str


class SearchResult(FunctionContract):
    query: str
    matched_count: int
    workspace_paths: list[str]
    matches: list[Match]
    sources: list[dict[str, Any]]
    summary: str


TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log", ".html"}
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_SNIPPET_CHARS = 500


def _operation(
    query: str,
    path: str | None = None,
    max_results: int = 10,
    context: OperationContext | None = None,
) -> dict[str, Any]:
    clean_query = str(query or "").strip()
    if len(clean_query) < 2:
        raise ValueError("query must contain at least two characters.")
    candidates = _select_files(context, path)
    terms = [term.lower() for term in re.findall(r"\w+", clean_query) if len(term) > 1]
    if not terms:
        raise ValueError("query must contain searchable words.")

    matches: list[dict[str, Any]] = []
    for item in candidates:
        source = _source_path(context, item)
        if not source or not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
            continue
        suffix = source.suffix.lower()
        if suffix == ".pdf":
            matches.extend(_search_pdf(source, item, terms, clean_query, max_results - len(matches)))
        elif suffix in TEXT_SUFFIXES:
            matches.extend(_search_text(source, item, terms, clean_query, max_results - len(matches)))
        if len(matches) >= max_results:
            break

    files = list(dict.fromkeys(str(item.get("workspace_path") or item.get("path") or "") for item in candidates if item))
    sources = []
    for match in matches:
        page_suffix = f" page {match['page']}" if match.get("page") else ""
        sources.append(
            {
                "title": f"{match['path']}{page_suffix}",
                "source": match["path"],
                "page": match.get("page"),
                "quote": match["excerpt"],
            }
        )
    return output({
        "query": clean_query,
        "matched_count": len(matches),
        "workspace_paths": files,
        "matches": matches,
        "sources": sources,
        "summary": f"Found {len(matches)} matching excerpt(s) in {len(files)} workspace file(s).",
    })


def _select_files(context: OperationContext, requested: str | None) -> list[dict[str, Any]]:
    files = context.files
    if not requested:
        return files
    requested = str(requested).strip()
    resolve_session_path(context, requested)
    exact = [
        item for item in files
        if requested in {str(item.get("workspace_path") or ""), str(item.get("path") or ""), str(item.get("name") or "")}
    ]
    if not exact:
        raise ValueError(f"No workspace file matches {requested!r}.")
    return exact


def _source_path(context: OperationContext, item: dict[str, Any]) -> Path | None:
    try:
        return resolve_workspace_item(context, item)[0]
    except (FileNotFoundError, ValueError):
        return None


def _search_text(source: Path, item: dict[str, Any], terms: list[str], query: str, limit: int) -> list[dict[str, Any]]:
    text = source.read_text(encoding="utf-8", errors="replace")
    results = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        if query.lower() not in lower and not all(term in lower for term in terms):
            continue
        results.append({"path": str(item.get("workspace_path") or item.get("path") or source.name), "line": line_number, "excerpt": _excerpt(line, terms)})
        if len(results) >= limit:
            break
    return results


def _search_pdf(source: Path, item: dict[str, Any], terms: list[str], query: str, limit: int) -> list[dict[str, Any]]:
    reader = PdfReader(str(source), strict=False)
    results = []
    for page_number, page in enumerate(reader.pages[:MAX_PDF_PAGES], start=1):
        text = (page.extract_text() or "").strip()
        lower = text.lower()
        if query.lower() not in lower and not all(term in lower for term in terms):
            continue
        results.append({"path": str(item.get("workspace_path") or item.get("path") or source.name), "page": page_number, "excerpt": _excerpt(text, terms)})
        if len(results) >= limit:
            break
    return results


def _excerpt(text: str, terms: list[str]) -> str:
    clean = " ".join(text.split())
    lower = clean.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 120)
    excerpt = clean[start : start + MAX_SNIPPET_CHARS].strip()
    return ("…" if start else "") + excerpt + ("…" if start + MAX_SNIPPET_CHARS < len(clean) else "")




@bio_function_tool()
async def workspace_search(
    ctx: RunContextWrapper[AgentRunContext],
    query: Annotated[str, Field(min_length=2, max_length=500)],
    path: Annotated[str | None, Field(description="Optional workspace-relative file path.")] = None,
    max_results: Annotated[int, Field(ge=1, le=50)] = 10,
) -> FunctionResult[SearchResult]:
    """Find bounded excerpts across uploaded text files and PDFs."""
    return await invoke(ctx.context, "workspace_search", _operation,
                              {"query": query, "path": path, "max_results": max_results}, FunctionResult[SearchResult])


__all__ = ["workspace_search"]
