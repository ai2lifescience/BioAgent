"""HTML and search-result parsing owned by the species-report tool."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse


def normalize_text(text: str) -> str:
    """Collapse HTML whitespace while preserving the actual words."""

    return re.sub(r"\s+", " ", text or "").strip()


def clean_duckduckgo_href(href: str) -> str | None:
    """Resolve a DuckDuckGo result link to its external HTTP(S) target."""

    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in (parsed.hostname or ""):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(target) if target else href
    if not href.startswith(("http://", "https://")):
        return None
    return href


def parse_duckduckgo_results(
    html: str,
    max_results: int,
    *,
    max_excerpt_chars: int = 900,
) -> list[dict[str, str]]:
    """Parse bounded result cards from DuckDuckGo's HTML endpoint."""

    if max_results <= 0:
        return []

    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise RuntimeError("beautifulsoup4 is required for trusted web collection.") from exc

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    nodes = soup.select(".result")
    if not nodes:
        nodes = [link.parent for link in soup.select("a.result__a") if link.parent]
    for node in nodes:
        link = node.select_one("a.result__a")
        if not link:
            continue
        href = clean_duckduckgo_href(str(link.get("href") or "").strip())
        if not href or href in seen:
            continue
        seen.add(href)
        snippet = node.select_one(".result__snippet")
        results.append(
            {
                "title": unescape(link.get_text(" ", strip=True))[:300],
                "url": href,
                "source": (urlparse(href).hostname or "").lower(),
                "excerpt": (
                    unescape(snippet.get_text(" ", strip=True))[:max_excerpt_chars]
                    if snippet
                    else ""
                ),
            }
        )
        if len(results) >= max_results:
            break
    return results


def extract_html_text(html: str, *, max_chars: int | None = None) -> tuple[str, str]:
    """Return a page title and readable body text with navigation removed."""

    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise RuntimeError("beautifulsoup4 is required for HTML parsing.") from exc

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form"]):
        tag.decompose()
    title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    body = soup.find("main") or soup.find("article") or soup.body or soup
    pieces = []
    for node in body.find_all(["h1", "h2", "h3", "p", "li"], recursive=True):
        text = normalize_text(node.get_text(" ", strip=True))
        if len(text) >= 30:
            pieces.append(text)
    text = "\n".join(pieces) if pieces else normalize_text(body.get_text(" ", strip=True))
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "…"
    return title, text


__all__ = [
    "clean_duckduckgo_href",
    "extract_html_text",
    "normalize_text",
    "parse_duckduckgo_results",
]
