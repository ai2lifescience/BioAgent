"""NCBI Entrez HTTP client helpers."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from bio_data.ncbi_entrez.spec import EUTILS_BASE_URL, REQUEST_RETRIES, REQUEST_TIMEOUT

def _base_params(email: str | None = None, api_key: str | None = None) -> dict[str, str]:
    params = {
        "tool": "bio_agent_ncbi_retrieval",
        "email": email or os.getenv("NCBI_EMAIL", "bio_agent@example.local"),
    }
    resolved_api_key = api_key or os.getenv("NCBI_API_KEY")
    if resolved_api_key:
        params["api_key"] = resolved_api_key
    return params

def _request_get(
    endpoint: str,
    params: dict[str, Any],
    stream: bool = False,
) -> requests.Response:
    url = f"{EUTILS_BASE_URL}/{endpoint}"
    last_error: Exception | None = None

    for attempt in range(REQUEST_RETRIES + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                stream=stream,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"NCBI request failed for {endpoint}: {last_error}")

def _search_ncbi(
    term: str,
    db: str,
    max_records: int,
    email: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        **_base_params(email=email, api_key=api_key),
        "db": db,
        "term": term,
        "retmode": "json",
        "retmax": 0,
        "usehistory": "y",
    }
    response = _request_get("esearch.fcgi", params)
    payload = response.json()
    search_result = payload.get("esearchresult", {})
    if "ERROR" in search_result:
        raise RuntimeError(f"NCBI ESearch error: {search_result['ERROR']}")

    count = int(search_result.get("count", 0))
    return {
        "count": count,
        "download_count": min(count, max_records),
        "query_key": search_result.get("querykey"),
        "webenv": search_result.get("webenv"),
        "query_translation": search_result.get("querytranslation"),
    }
