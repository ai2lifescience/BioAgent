"""Bounded HTTP transport shared by external tool adapters.

This module owns transport mechanics only: HTTPS validation, retries, response
size limits, and provenance timestamps. Each adapter supplies its own host
allowlist and therefore keeps ownership of its external service policy.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Any
from urllib.parse import urlparse

import requests


REQUEST_TIMEOUT = 30
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_USER_AGENT = "BioAgent/1.0"


def validate_https_url(url: str, *, allowed_hosts: Collection[str]) -> str:
    """Reject non-HTTPS URLs and hosts outside the caller's policy."""

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    normalized_hosts = {str(host).lower().rstrip(".") for host in allowed_hosts}
    if parsed.scheme != "https":
        raise ValueError("External API URLs must use HTTPS.")
    if hostname not in normalized_hosts:
        raise ValueError(f"External API host is not allowlisted: {hostname or 'missing host'}.")
    return url


def request_http(
    method: str,
    url: str,
    *,
    allowed_hosts: Collection[str],
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    accept: str = "application/json",
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = REQUEST_TIMEOUT,
    retries: int = 2,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> requests.Response:
    """Call an allowlisted HTTPS endpoint with bounded retries and size."""

    validate_https_url(url, allowed_hosts=allowed_hosts)
    headers = {"Accept": accept, "User-Agent": user_agent}
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
        raise RuntimeError("HTTP request produced no response.")
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_response_bytes:
                raise RuntimeError("HTTP response exceeded the configured size limit.")
        except ValueError:
            pass
    if len(response.content) > max_response_bytes:
        raise RuntimeError("HTTP response exceeded the configured size limit.")
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
    """Return a common source record for an adapter response."""

    return {
        "endpoint": url,
        "operation": operation,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "DEFAULT_USER_AGENT",
    "MAX_RESPONSE_BYTES",
    "REQUEST_TIMEOUT",
    "RETRY_STATUS_CODES",
    "request_http",
    "response_provenance",
    "validate_https_url",
]
