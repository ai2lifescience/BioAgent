"""Small, citation-preserving web research workflow.

This intentionally uses bounded HTTP requests instead of giving the model an
unrestricted shell or browser. Search results and fetched excerpts are returned
as evidence for the final answer.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import quote_plus, urljoin, urlparse
import socket
from typing import Any

import requests
from tools.infrastructure.tooling.context import WorkflowContext, ensure_workflow_context
from .parsing import extract_html_text, parse_duckduckgo_results


SEARCH_URL = "https://html.duckduckgo.com/html/?q={}"
USER_AGENT = "Pipeline2Agent/1.0 (+https://github.com/ai2lifescience/BioAgent)"
MAX_RESPONSE_BYTES = 1_500_000
MAX_EXCERPT_CHARS = 900


def web_research(
    query: str,
    domains: list[str] | None = None,
    max_sources: int = 5,
    fetch_content: bool = True,
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "web_research")
    query = str(query or "").strip()
    if len(query) < 3:
        raise ValueError("query must contain at least three characters.")
    limit = min(max(int(max_sources), 1), 10)
    allowed_domains = _normalize_domains(domains)
    response = _request(SEARCH_URL.format(quote_plus(query)))
    results = _search_results(response.text, allowed_domains, limit)
    sources = []
    for item in results:
        source = dict(item)
        if fetch_content:
            try:
                page = _request(item["url"])
                source["excerpt"] = _page_excerpt(page.text)
                source["content_status"] = "fetched"
            except (OSError, ValueError, requests.RequestException) as exc:
                source["content_status"] = "unavailable"
                source["fetch_error"] = str(exc)[:240]
        sources.append(source)
    return {
        "status": "ok",
        "query": query,
        "source_count": len(sources),
        "sources": sources,
        "urls": [source["url"] for source in sources],
        "summary": f"Collected {len(sources)} web source(s) for {query!r}.",
    }


def _request(url: str, _redirects: int = 0) -> requests.Response:
    hostname = (urlparse(url).hostname or "").lower()
    # The search provider may resolve through a local network proxy in managed
    # environments. Search redirects are still validated normally.
    _validate_url(url, allow_private_dns=_redirects == 0 and hostname in {"html.duckduckgo.com", "www.duckduckgo.com"})
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=(5, 20),
        allow_redirects=False,
        stream=True,
    )
    if 300 <= response.status_code < 400:
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise ValueError("Web source returned a redirect without a location.")
        if _redirects >= 3:
            raise ValueError("Web source exceeded the redirect limit.")
        return _request(urljoin(url, location), _redirects + 1)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        response.close()
        raise ValueError("Web source is not an HTML or text page.")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            response.close()
            raise ValueError("Web source exceeded the response size limit.")
    response.close()
    response._content = bytes(body)
    return response


def _search_results(html: str, domains: set[str], limit: int) -> list[dict[str, str]]:
    parsed_results = parse_duckduckgo_results(html, max(limit * 2, limit), max_excerpt_chars=MAX_EXCERPT_CHARS)
    results: list[dict[str, str]] = []
    for item in parsed_results:
        href = item["url"]
        try:
            _validate_url(href)
        except ValueError:
            continue
        hostname = (urlparse(href).hostname or "").lower()
        if domains and not any(hostname == domain or hostname.endswith("." + domain) for domain in domains):
            continue
        item["source"] = hostname
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _page_excerpt(html: str) -> str:
    _title, text = extract_html_text(html, max_chars=MAX_EXCERPT_CHARS)
    return " ".join(text.split())


def _normalize_domains(domains: list[str] | None) -> set[str]:
    normalized = set()
    for value in domains or []:
        domain = str(value).strip().lower().rstrip(".")
        if domain.startswith("http://") or domain.startswith("https://"):
            domain = urlparse(domain).hostname or ""
        if domain and all(char.isalnum() or char in ".-_" for char in domain):
            normalized.add(domain)
    return normalized


def _validate_url(url: str, *, allow_private_dns: bool = False) -> None:
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only http(s) web sources are allowed.")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Local web sources are not allowed.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)}
        except OSError as exc:
            raise ValueError(f"Could not resolve web source host: {host}") from exc
    if not allow_private_dns and any(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved for address in addresses):
        raise ValueError("Private or local web sources are not allowed.")


__all__ = ["web_research"]
