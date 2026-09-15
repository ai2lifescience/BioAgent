"""HTML parsing helpers for trusted web collection."""

from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_html_text(html: str) -> tuple[str, str]:
    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise RuntimeError("beautifulsoup4 is required for HTML parsing.") from exc

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "form"]):
        tag.decompose()

    title = normalize_text(soup.title.string if soup.title else "")
    body = soup.find("main") or soup.find("article") or soup.body or soup
    pieces = []
    for node in body.find_all(["h1", "h2", "h3", "p", "li"], recursive=True):
        text = normalize_text(node.get_text(" ", strip=True))
        if len(text) >= 30:
            pieces.append(text)
    if not pieces:
        pieces = [normalize_text(body.get_text(" ", strip=True))]
    return title, "\n".join(pieces)
