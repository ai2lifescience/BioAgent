"""Workflow wrapper for reading a PDF from the session workspace."""

from __future__ import annotations

from typing import Any

from tools.common.context import WorkflowContext, ensure_workflow_context

from .extraction import read_pdf_text


def document_read(
    path: str | None = None,
    page_start: int = 1,
    page_end: int | None = None,
    char_offset: int = 0,
    max_chars: int = 40000,
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "document_read")
    source, display_path = _resolve_workspace_file(path, context)

    def _read(**arguments: Any) -> dict[str, Any]:
        # Keep the host-side resolved path out of tool evidence. The model and
        # UI should only see the workspace-relative path it supplied.
        arguments.pop("path", None)
        return read_pdf_text(path=str(source), **arguments)

    result = context.call(
        "document_read",
        _read,
        {
            "path": path,
            "display_path": display_path,
            "page_start": page_start,
            "page_end": page_end,
            "char_offset": char_offset,
            "max_chars": max_chars,
        },
    )["result"]
    return {
        "workflow": "document_read",
        "tool": "document_read",
        "answer": _answer(result, display_path),
        "summary": _summary(result, display_path),
        "source_path": display_path,
        **result,
    }


def _resolve_workspace_file(path: str | None, context: WorkflowContext):
    requested = str(path or "").strip()
    candidates = context.files
    if requested:
        exact = []
        named = []
        for item in candidates:
            item_candidates = {
                str(item.get("workspace_path") or ""),
                str(item.get("path") or ""),
            }
            if requested in item_candidates:
                exact.append(item)
            elif requested == str(item.get("name") or ""):
                named.append(item)
        matches = exact or named
    else:
        matches = [
            item for item in candidates
            if str(item.get("workspace_path") or item.get("path") or "").lower().endswith(".pdf")
        ]
    if not matches:
        if requested:
            raise ValueError(
                "The requested path is not a PDF in the active workspace. "
                "Use an exact workspace_path from the workspace listing."
            )
        raise ValueError("No uploaded PDF is available in the active workspace.")

    item = max(matches, key=lambda value: int(value.get("modified_at") or 0))
    selected_path = str(item.get("workspace_path") or item.get("path") or "")
    display_path = str(item.get("workspace_path") or selected_path)
    source = str(item.get("path") or "")
    if not source:
        raise ValueError(f"Workspace file is not available: {display_path}")
    from pathlib import Path

    resolved = Path(source).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Workspace file is not available: {display_path}")
    if resolved.suffix.lower() != ".pdf":
        raise ValueError("document_read accepts PDF files only.")
    return resolved, display_path


def _answer(result: dict[str, Any], path: str) -> str:
    status = result.get("status", "ok")
    if status == "ocr_required":
        return (
            f"The PDF {path} appears to be scanned and has no selectable text. "
            "OCR is required before it can be summarized."
        )
    if not result.get("text"):
        return f"No selectable text was found in {path}."
    return (
        f"Read pages {result.get('pages_read', 0)} of {result.get('page_count', 0)} "
        f"from {path}. The extracted text is in the `text` field with page "
        "markers for citation."
    )


def _summary(result: dict[str, Any], path: str) -> str:
    if result.get("status") == "ocr_required":
        return f"PDF text extraction found no selectable text in {path}; OCR is required."
    if result.get("truncated"):
        return (
            f"Read {result.get('pages_read', 0)} of {result.get('page_count', 0)} "
            f"pages from {path}; more pages are available starting at page "
            f"{result.get('next_page_start')} at character offset "
            f"{result.get('next_char_offset', 0)}."
        )
    return f"Read {result.get('pages_read', 0)} page(s) of selectable text from {path}."
