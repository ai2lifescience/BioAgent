"""Shared HTTP helpers for allowlisted biological database APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Any
from urllib.parse import urlparse

import requests


REQUEST_TIMEOUT = 30
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
ALLOWED_API_HOSTS = {
    "alphafold.ebi.ac.uk",
    "data.rcsb.org",
    "files.rcsb.org",
    "ftp.ebi.ac.uk",
    "rest.kegg.jp",
    "search.rcsb.org",
    "www.alphafold.ebi.ac.uk",
    "www.ebi.ac.uk",
}
USER_AGENT = "BioAgent/1.0 (biological database client)"


def validate_api_url(url: str) -> str:
    """Reject non-HTTPS and non-allowlisted API URLs."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError("Biological database API URLs must use HTTPS.")
    if hostname not in ALLOWED_API_HOSTS:
        raise ValueError(f"Biological database API host is not allowlisted: {hostname or 'missing host'}.")
    return url


def request_api(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    accept: str = "application/json",
    timeout: int = REQUEST_TIMEOUT,
    retries: int = 2,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> requests.Response:
    """Call an official API with bounded retries and response size."""
    validate_api_url(url)
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    response: requests.Response | None = None
    for attempt in range(retries + 1):
        response = requests.request(
            method.upper(),
            url,
            params=params,
            json=json_data,
            headers=headers,
            timeout=timeout,
        )
        if response.status_code not in RETRY_STATUS_CODES or attempt >= retries:
            break
        time.sleep(_retry_delay(response, attempt))

    if response is None:  # pragma: no cover - defensive guard
        raise RuntimeError("Biological database API request produced no response.")
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_response_bytes:
                raise RuntimeError("Biological database API response exceeded the configured size limit.")
        except ValueError:
            pass
    if len(response.content) > max_response_bytes:
        raise RuntimeError("Biological database API response exceeded the configured size limit.")
    return response


def _retry_delay(response: requests.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After", "").strip()
    if value:
        try:
            return min(max(float(value), 0.0), 5.0)
        except ValueError:
            try:
                target = parsedate_to_datetime(value).timestamp()
                return min(max(target - time.time(), 0.0), 5.0)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(0.25 * (2**attempt), 2.0)


def response_provenance(url: str, operation: str) -> dict[str, str]:
    return {
        "endpoint": url,
        "operation": operation,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
