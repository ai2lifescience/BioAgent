"""Bounded, SSRF-aware web discovery and page extraction for knowledge jobs."""
from __future__ import annotations

import asyncio
from collections import deque
import ipaddress
import os
import re
import socket
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

import httpx2
from bs4 import BeautifulSoup

from ..models import KnowledgePage


MAX_SEARCH_BYTES = 4 * 1024 * 1024
MAX_PAGE_BYTES = 1_500_000
MAX_PAGE_CHARS = 60_000
USER_AGENT = "Pipeline2Agent-Knowledge/1.0"


def canonical_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Knowledge sources must use public HTTP(S) URLs.")
    host = parsed.hostname.lower().rstrip(".")
    if parsed.username or parsed.password:
        raise ValueError("Knowledge URLs must not contain credentials.")
    port = parsed.port
    if (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443):
        port = None
    authority = f"[{host}]" if ":" in host else host
    netloc = authority if port is None else f"{authority}:{port}"
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))


def validate_domains(domains: list[str]) -> list[str]:
    normalized = [str(value).strip().lower().rstrip(".") for value in domains if str(value).strip()]
    if any(not re.fullmatch(r"[a-z0-9.-]+", value) for value in normalized):
        raise ValueError("allowed_domains must contain hostnames only.")
    if any(".." in value or value.startswith(".") or value.endswith(".") for value in normalized):
        raise ValueError("allowed_domains contains an invalid hostname.")
    return sorted(set(normalized))


def _allowed(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return bool(host) and (not domains or any(host == domain or host.endswith("." + domain) for domain in domains))


async def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("Knowledge sources must be public HTTP(S) URLs without credentials.")
    if host.lower().rstrip(".") in {"localhost", "localhost.localdomain"}:
        raise ValueError("Private web addresses are not permitted.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            addresses = {ipaddress.ip_address(item[4][0]) for item in infos}
        except OSError:
            raise ValueError("Web hostname could not be resolved.") from None
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Private web addresses are not permitted.")


def _client_options() -> dict:
    if os.getenv("AGENT_DISABLE_PROXY", "").lower() in {"1", "true", "yes"}:
        return {"trust_env": False}
    proxy = os.getenv("AGENT_PROXY") or os.getenv("ALL_PROXY") or os.getenv("all_proxy")
    if proxy:
        if proxy.startswith("socks://"):
            proxy = "socks5://" + proxy[len("socks://"):]
        return {"trust_env": False, "proxy": proxy}
    return {"trust_env": True}


async def _read_response(response, *, max_bytes: int) -> str:
    data = bytearray()
    async for chunk in response.aiter_bytes():
        data.extend(chunk)
        if len(data) > max_bytes:
            raise ValueError("Web source exceeds the configured byte limit.")
    return data.decode(response.encoding or "utf-8", errors="replace")


async def fetch_page(url: str, *, allowed_domains: list[str] | None = None) -> tuple[str, str]:
    current = canonical_url(url)
    async with httpx2.AsyncClient(timeout=20, follow_redirects=False, **_client_options()) as client:
        for redirect in range(4):
            if allowed_domains and not _allowed(current, allowed_domains):
                raise ValueError("Redirected source is outside the allowed domains.")
            await _validate_url(current)
            async with client.stream("GET", current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/xhtml+xml"}) as response:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location")
                    if not location or redirect == 3:
                        raise ValueError("Web source has an invalid redirect or exceeded three redirects.")
                    current = canonical_url(urljoin(current, location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                    raise ValueError("Web source is not an HTML or text page.")
                return current, await _read_response(response, max_bytes=MAX_PAGE_BYTES)
    raise ValueError("Web source could not be fetched.")


def extract_page(url: str, raw: str, *, depth: int) -> tuple[KnowledgePage, list[str]]:
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else url
    links: list[str] = []
    for node in soup.select("a[href]"):
        try:
            link = canonical_url(urljoin(url, str(node.get("href", ""))))
        except ValueError:
            continue
        if link not in links:
            links.append(link)
    for element in soup(["script", "style", "nav", "footer", "noscript", "header", "form"]):
        element.decompose()
    text = "\n".join(line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("Web page has no readable text.")
    return KnowledgePage(url=url, title=title[:300], text=text[:MAX_PAGE_CHARS], depth=depth), links


async def discover(query: str, domains: list[str], limit: int) -> list[str]:
    """Discover bounded public URLs through DuckDuckGo result pages."""
    term = query + (" (" + " OR ".join(f"site:{domain}" for domain in domains) + ")" if domains else "")
    async with httpx2.AsyncClient(timeout=20, follow_redirects=False, **_client_options()) as client:
        async with client.stream("GET", "https://html.duckduckgo.com/html/", params={"q": term}, headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            html = await _read_response(response, max_bytes=MAX_SEARCH_BYTES)
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for node in soup.select(".result a.result__a"):
        raw_url = str(node.get("href", ""))
        parsed = urlparse(raw_url)
        if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}:
            raw_url = unquote(parse_qs(parsed.query).get("uddg", [raw_url])[0])
        try:
            value = canonical_url(raw_url)
        except ValueError:
            continue
        if _allowed(value, domains) and value not in found:
            found.append(value)
        if len(found) >= limit:
            break
    return found


async def crawl(
    *,
    request: str,
    seed_urls: list[str],
    allowed_domains: list[str],
    max_pages: int,
    max_depth: int,
    progress=None,
) -> list[KnowledgePage]:
    domains = validate_domains(allowed_domains)
    seeds = [canonical_url(url) for url in seed_urls]
    if domains and any(not _allowed(url, domains) for url in seeds):
        raise ValueError("Every seed URL must match allowed_domains.")
    if not seeds:
        seeds = await discover(request, domains, min(max_pages, 10))
    if not seeds:
        raise ValueError("No public sources were discovered for the request.")
    # A crawl without an explicit allowlist stays on the seed hosts.  This
    # prevents one page from turning a user request into an open web crawl.
    if not domains:
        domains = sorted({urlparse(url).hostname.lower().rstrip(".") for url in seeds if urlparse(url).hostname})

    queue = deque((url, 0) for url in seeds)
    seen: set[str] = set()
    pages: list[KnowledgePage] = []
    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        if url in seen or not _allowed(url, domains):
            continue
        seen.add(url)
        try:
            final_url, raw = await fetch_page(url, allowed_domains=domains)
            if not _allowed(final_url, domains):
                raise ValueError("Redirected source is outside the allowed domains.")
            page, links = extract_page(final_url, raw, depth=depth)
        except (httpx2.HTTPError, OSError, ValueError) as exc:
            if progress:
                progress({"url": url, "skipped": 1, "message": str(exc)[:300]})
            continue
        if any(existing.url == page.url for existing in pages):
            continue
        pages.append(page)
        if progress:
            progress({"url": page.url, "fetched": len(pages), "depth": depth})
        if depth < max_depth:
            for link in links:
                if link not in seen and _allowed(link, domains):
                    queue.append((link, depth + 1))
    return pages


__all__ = ["canonical_url", "crawl", "discover", "extract_page", "fetch_page", "validate_domains"]
