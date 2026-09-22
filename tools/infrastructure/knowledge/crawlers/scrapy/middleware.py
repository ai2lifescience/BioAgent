"""Basic public-host checks for Scrapy requests and redirects."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from scrapy.exceptions import IgnoreRequest


def _public(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(
                    host,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except OSError:
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


class PublicUrlMiddleware:
    def process_request(self, request, spider):
        if not _public(request.url):
            raise IgnoreRequest("Scrapy request is not a public HTTP(S) URL.")

    def process_response(self, request, response, spider):
        if not _public(response.url):
            raise IgnoreRequest("Scrapy response redirected to a private URL.")
        return response


__all__ = ["PublicUrlMiddleware"]
