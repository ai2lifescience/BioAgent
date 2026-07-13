"""Trusted web search helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from tools.web.constants import DUCKDUCKGO_HTML_URL
from tools.web.http import request_get
from tools.web.trust import trusted_host


def clean_duckduckgo_href(href: str) -> str | None:
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


def duckduckgo_search(query: str, max_results: int) -> list[str]:
    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "beautifulsoup4 is required for trusted web source collection."
        ) from exc

    response = request_get(
        DUCKDUCKGO_HTML_URL,
        params={"q": query},
        timeout=10,
        retries=0,
    )
    soup = BeautifulSoup(response.text, "lxml")
    urls: list[str] = []
    for link in soup.select("a.result__a, a[href]"):
        href = clean_duckduckgo_href(link.get("href", ""))
        if not href or not trusted_host(href):
            continue
        if href not in urls:
            urls.append(href)
        if len(urls) >= max_results:
            break
    return urls
