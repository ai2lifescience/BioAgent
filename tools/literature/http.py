"""HTTP helpers for PubMed collection."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from tools.literature.constants import DEFAULT_USER_AGENT, REQUEST_RETRIES, REQUEST_TIMEOUT


def base_ncbi_params(email: str | None = None, api_key: str | None = None) -> dict[str, str]:
    params = {
        "tool": "bio_agent_species_knowledge",
        "email": email or os.getenv("NCBI_EMAIL", "bio_agent@example.local"),
    }
    resolved_api_key = api_key or os.getenv("NCBI_API_KEY")
    if resolved_api_key:
        params["api_key"] = resolved_api_key
    return params


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
