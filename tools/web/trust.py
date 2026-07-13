"""Trusted-domain checks for web collection."""

from __future__ import annotations

from urllib.parse import urlparse

from tools.web.constants import TRUSTED_WEB_DOMAINS


def trusted_host(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    for domain in TRUSTED_WEB_DOMAINS:
        if host == domain or host.endswith(f".{domain}"):
            return domain
    return None
