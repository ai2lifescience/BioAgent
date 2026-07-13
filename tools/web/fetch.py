"""Trusted web page fetch helpers."""

from __future__ import annotations

from typing import Any

from tools.web.http import request_get
from tools.web.parse import extract_html_text, normalize_text
from tools.web.trust import trusted_host


def fetch_trusted_web_page(url: str, species_name: str) -> dict[str, Any] | None:
    host = trusted_host(url)
    if not host:
        return None
    try:
        response = request_get(url, timeout=15, retries=0)
    except Exception:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "<html" not in response.text[:500].lower():
        return None

    title, text = extract_html_text(response.text)
    text = normalize_text(text)
    if len(text) < 250:
        return None
    return {
        "species": species_name,
        "source": host,
        "title": title or host,
        "url": url,
        "verified": True,
        "text": text[:18000],
        "metadata": {
            "source_type": "authority_web",
            "host": host,
        },
    }
