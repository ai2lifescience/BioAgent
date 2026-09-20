"""Trusted web search helpers."""

from __future__ import annotations

from tools.function_tools.species_report.web.constants import DUCKDUCKGO_HTML_URL
from tools.function_tools.species_report.web.http import request_get
from tools.function_tools.species_report.web.trust import trusted_host
from tools.function_tools.species_report.web.parse import clean_duckduckgo_href, parse_duckduckgo_results




def duckduckgo_search(query: str, max_results: int) -> list[str]:
    response = request_get(
        DUCKDUCKGO_HTML_URL,
        params={"q": query},
        timeout=10,
        retries=0,
    )
    urls: list[str] = []
    for item in parse_duckduckgo_results(response.text, max_results):
        href = clean_duckduckgo_href(item["url"])
        if not href or not trusted_host(href):
            continue
        if href not in urls:
            urls.append(href)
        if len(urls) >= max_results:
            break
    return urls
