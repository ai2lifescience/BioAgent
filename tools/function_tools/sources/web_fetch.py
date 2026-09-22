"""Fetch one public HTML/text page as a bounded evidence artifact."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from typing import Annotated

import httpx2
from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import write_json, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.evidence_models import EvidenceRecord
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract as Contract, FunctionResult as Result



import asyncio
import ipaddress
import socket
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

MAX_RESPONSE_BYTES = 1_500_000


class SearchResult(Contract):
    query: str
    evidence_path: str
    sources: list[EvidenceRecord]
    returned: int
    total: int | None = None
    truncated: bool


def record(title, url, source, text, **kwargs):
    return EvidenceRecord(id="ev_" + hashlib.sha256((url + "\n" + text).encode()).hexdigest()[:20],
                          title=title, url=url, source=source, text=text,
                          retrieved_at=datetime.now(timezone.utc).isoformat(), **kwargs)


def save_search(context, query, records, total):
    file = write_json(context, "evidence.json", {"schema_version": 1, "sources": [r.model_dump(mode="json") for r in records]})
    preview = [r.model_copy(update={"text": r.text[:1000]}).model_dump(mode="json") for r in records]
    return output({"query": query, "evidence_path": file["path"], "sources": preview,
                   "total": total, "returned": len(records),
                   "truncated": (total is not None and total > len(records)) or any(len(r.text) > 1000 for r in records)}, file)


async def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("Provide a public HTTP(S) URL without credentials.")
    if host.lower().rstrip(".") in {"localhost", "localhost.localdomain"}:
        raise ValueError("Private web addresses are not permitted.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            addresses = {ipaddress.ip_address(item[4][0]) for item in infos}
        except OSError:
            raise ValueError("Web hostname could not be resolved.") from None
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Private web addresses are not permitted.")


async def _fetch(url: str) -> tuple[str, str]:
    options = {"trust_env": True}
    if os.getenv("AGENT_DISABLE_PROXY", "").lower() in {"1", "true", "yes"}:
        options = {"trust_env": False}
    else:
        proxy = os.getenv("AGENT_PROXY") or os.getenv("ALL_PROXY") or os.getenv("all_proxy")
        if proxy:
            proxy = "socks5://" + proxy[len("socks://"):] if proxy.startswith("socks://") else proxy
            options = {"trust_env": False, "proxy": proxy}
    async with httpx2.AsyncClient(timeout=20, follow_redirects=False, **options) as client:
        for redirects in range(4):
            await _validate_url(url)
            async with client.stream("GET", url, headers={"User-Agent": "Pipeline2Agent/1.0", "Accept": "text/html,text/plain"}) as response:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location")
                    if not location or redirects == 3:
                        raise ValueError("Web source has an invalid redirect or exceeded three redirects.")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                    raise ValueError("Web source is not an HTML or text page.")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise ValueError("Web source exceeds 1.5 MB.")
                return url, data.decode(response.encoding or "utf-8", errors="replace")
    raise ValueError("Web source could not be fetched.")


async def _operation(*, url: str, max_chars: int, context):
    try:
        final_url, html = await _fetch(url)
    except httpx2.HTTPError:
        raise RuntimeError("Web page request failed; retry later.") from None
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else final_url
    for element in soup(["script", "style", "nav", "footer", "noscript"]):
        element.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    if not text:
        raise ValueError("Web page has no readable text.")
    result = save_search(context, url, [record(title[:300], final_url, urlparse(final_url).hostname, text[:max_chars])], 1)
    result["data"]["truncated"] |= len(text) > max_chars
    return result


@bio_function_tool(timeout=120)
async def web_fetch(
    ctx: RunContextWrapper[AgentRunContext],
    url: Annotated[str, Field(min_length=1, max_length=4000)],
    max_chars: Annotated[int, Field(ge=100, le=60000)] = 20000,
) -> Result[SearchResult]:
    """Fetch one public HTML/text page; save readable text as evidence for retrieval or synthesis."""
    return await invoke(ctx.context, "web_fetch", _operation, {"url": url, "max_chars": max_chars}, Result[SearchResult])


__all__ = ["web_fetch"]
