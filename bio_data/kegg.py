"""Deterministic KEGG REST API adapter."""

from __future__ import annotations

import re
from threading import Lock
import time
from typing import Any
from urllib.parse import quote

from bio_data.api_http import request_api, response_provenance


KEGG_BASE_URL = "https://rest.kegg.jp"
ALLOWED_OPERATIONS = {"info", "list", "find", "get", "conv", "link"}
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.:+\- ]+$")
_RATE_LOCK = Lock()
_LAST_REQUEST = 0.0
_MIN_INTERVAL = 1.0 / 3.0


def query_kegg(
    query: str,
    max_results: int = 5,
    operation: str | None = None,
) -> dict[str, Any]:
    clean_query = query.strip().strip("/")
    if not clean_query:
        raise ValueError("KEGG query must not be empty.")
    clean_operation = (operation or "get").strip().lower()
    if clean_operation not in ALLOWED_OPERATIONS:
        allowed = ", ".join(sorted(ALLOWED_OPERATIONS))
        raise ValueError(f"KEGG operation must be one of: {allowed}.")

    components = [part.strip() for part in clean_query.split("/") if part.strip()]
    if not components or any(not _SAFE_COMPONENT.fullmatch(part) for part in components):
        raise ValueError("KEGG query contains unsupported characters.")
    encoded = "/".join(quote(part.replace(" ", "+"), safe="+:._-") for part in components)
    url = f"{KEGG_BASE_URL}/{clean_operation}/{encoded}"

    _throttle()
    response = request_api("GET", url, accept="text/plain")
    raw_text = response.text
    limit = max(1, min(int(max_results), 100))
    records = _parse_kegg_response(clean_operation, raw_text, limit)
    return {
        "database": "kegg",
        "query": clean_query,
        "operation": clean_operation,
        "record_count": len(records),
        "records": records,
        "raw_text": raw_text,
        "provenance": response_provenance(url, clean_operation),
        "warnings": [
            "The public KEGG REST API is restricted to academic use and should be called at no more than three requests per second."
        ],
    }


def _throttle() -> None:
    global _LAST_REQUEST
    with _RATE_LOCK:
        now = time.monotonic()
        remaining = _MIN_INTERVAL - (now - _LAST_REQUEST)
        if remaining > 0:
            time.sleep(remaining)
        _LAST_REQUEST = time.monotonic()


def _parse_kegg_response(operation: str, text: str, limit: int) -> list[dict[str, Any]]:
    if operation == "get":
        return _parse_flat_files(text)[:limit]
    records = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        left, separator, right = clean.partition("\t")
        records.append({"id": left, "value": right if separator else ""})
        if len(records) >= limit:
            break
    return records


def _parse_flat_files(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    last_key: str | None = None
    for line in text.splitlines():
        if line.strip() == "///":
            if current:
                records.append(current)
            current = {}
            last_key = None
            continue
        key = line[:12].strip()
        value = line[12:].strip()
        if key:
            last_key = key.lower()
            if last_key in current:
                previous = current[last_key]
                current[last_key] = previous + [value] if isinstance(previous, list) else [previous, value]
            else:
                current[last_key] = value
        elif last_key and value:
            previous = current.get(last_key, "")
            current[last_key] = previous + [value] if isinstance(previous, list) else [previous, value]
    if current:
        records.append(current)
    return records
