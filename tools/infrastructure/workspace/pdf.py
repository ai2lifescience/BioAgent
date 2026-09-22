"""Bounded, page-aware PDF text extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader

MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_PDF_PAGES = 2000


def read_pdf_text(
    path: str,
    display_path: str | None = None,
    page_start: int = 1,
    page_end: int | None = None,
    char_offset: int = 0,
    max_chars: int = 40000,
) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if source.suffix.lower() != ".pdf":
        raise ValueError("document_read accepts PDF files only.")
    if source.stat().st_size > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds the document reader limit of {MAX_PDF_BYTES} bytes.")
    if page_start < 1:
        raise ValueError("page_start must be at least 1.")
    if page_end is not None and page_end < page_start:
        raise ValueError("page_end must be greater than or equal to page_start.")
    if char_offset < 0:
        raise ValueError("char_offset must not be negative.")

    reader = PdfReader(str(source), strict=False)
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds the document reader limit of {MAX_PDF_PAGES} pages.")
    if page_count == 0:
        return {
            "status": "ocr_required",
            "page_count": 0,
            "pages_read": 0,
            "text": "",
            "truncated": False,
        }

    if page_start > page_count:
        raise ValueError(f"page_start {page_start} exceeds the PDF page count ({page_count}).")

    first = min(page_start, page_count)
    last = min(page_end or page_count, page_count)
    pieces: list[str] = []
    characters = 0
    pages_read = 0
    next_page_start: int | None = None
    next_char_offset: int | None = None

    for index in range(first - 1, last):
        page_text = (reader.pages[index].extract_text() or "").strip()
        offset = char_offset if index == first - 1 else 0
        if offset > len(page_text):
            raise ValueError(f"char_offset {offset} exceeds the text length of page {index + 1}.")
        page_text = page_text[offset:]
        if not page_text:
            continue
        marker = f"\n\n[Page {index + 1}]\n"
        available = max_chars - characters - len(marker)
        if available <= 0:
            next_page_start = index + 1
            break
        if len(page_text) > available:
            pieces.append(marker + page_text[:available].rstrip())
            characters += len(marker) + available
            pages_read += 1
            next_page_start = index + 1
            next_char_offset = offset + available
            break
        pieces.append(marker + page_text)
        characters += len(marker) + len(page_text)
        pages_read += 1

    text = "".join(pieces).strip()
    if next_page_start is None and last < page_count:
        next_page_start = last + 1
        next_char_offset = 0
    truncated = next_page_start is not None
    result: dict[str, Any] = {
        "status": "ok" if text else "ocr_required",
        "path": display_path or str(source),
        "page_count": page_count,
        "page_start": first,
        "page_end": last,
        "pages_read": pages_read,
        "characters": len(text),
        "text": text,
        "truncated": truncated,
    }
    if next_page_start is not None:
        result["next_page_start"] = next_page_start
        result["next_char_offset"] = next_char_offset or 0
    return result
