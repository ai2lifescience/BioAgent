"""HTTP helpers for trusted web collection."""

from __future__ import annotations

import time
from typing import Any

import requests

from tools.web.constants import DEFAULT_USER_AGENT, REQUEST_RETRIES, REQUEST_TIMEOUT


def request_get(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = REQUEST_TIMEOUT,
    retries: int = REQUEST_RETRIES,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Request failed for {url}: {last_error}")
