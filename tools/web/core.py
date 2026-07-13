"""Trusted web collection facade."""

from __future__ import annotations

from typing import Any

from tools.web.constants import TRUSTED_WEB_DOMAINS
from tools.web.fetch import fetch_trusted_web_page
from tools.web.search import duckduckgo_search


def collect_trusted_web_records(
    species_name: str,
    question: str,
    max_pages: int = 6,
) -> dict[str, Any]:
    if max_pages <= 0:
        return {
            "status": "ok",
            "species_name": species_name,
            "record_count": 0,
            "records": [],
            "candidate_urls": [],
        }

    per_domain = max(1, min(3, max_pages))
    candidate_urls: list[str] = []
    for domain in TRUSTED_WEB_DOMAINS:
        if len(candidate_urls) >= max_pages * 2:
            break
        query = f"site:{domain} {species_name} {question}"
        try:
            urls = duckduckgo_search(query, max_results=per_domain)
        except Exception:
            urls = []
        for url in urls:
            if url not in candidate_urls:
                candidate_urls.append(url)

    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for url in candidate_urls:
        if len(records) >= max_pages:
            break
        if url in seen_urls:
            continue
        seen_urls.add(url)
        record = fetch_trusted_web_page(url, species_name)
        if record:
            records.append(record)
    return {
        "status": "ok",
        "species_name": species_name,
        "record_count": len(records),
        "records": records,
        "candidate_urls": candidate_urls,
    }
