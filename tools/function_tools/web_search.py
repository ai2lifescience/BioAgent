"""Self-contained SDK capability: web_search."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import re
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


MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class SearchResult(Contract):
    query: str
    evidence_path: str
    sources: list[EvidenceRecord]
    returned: int
    total: int | None = None
    truncated: bool


async def request(url: str, params: dict) -> str:
    options = {"trust_env": True}
    if os.getenv("AGENT_DISABLE_PROXY", "").lower() in {"1", "true", "yes"}:
        options = {"trust_env": False}
    else:
        proxy = os.getenv("AGENT_PROXY") or os.getenv("ALL_PROXY") or os.getenv("all_proxy")
        if proxy:
            # HTTPX uses the explicit SOCKS version, unlike requests' socks alias.
            proxy = "socks5://" + proxy[len("socks://"):] if proxy.startswith("socks://") else proxy
            options = {"trust_env": False, "proxy": proxy}
    async with httpx2.AsyncClient(timeout=20, follow_redirects=False, **options) as client:
        async with client.stream("GET", url, params=params, headers={"User-Agent": "Pipeline2Agent/1.0"}) as response:
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError("Search endpoint returned an unexpected redirect.")
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_RESPONSE_BYTES:
                    raise ValueError("Search response exceeds 4 MB.")
            return chunks.decode("utf-8", errors="replace")


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


async def _operation(*, query: str, domains: list[str], max_sources: int, context):
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, parse_qs, unquote
    normalized = [domain.lower().strip() for domain in domains]
    if any(not re.fullmatch(r"[a-z0-9.-]+", domain) for domain in normalized):
        raise ValueError("domains must contain hostnames only.")
    term = query + (" (" + " OR ".join(f"site:{d}" for d in normalized) + ")" if normalized else "")
    html = await request("https://html.duckduckgo.com/html/", {"q": term})
    soup = BeautifulSoup(html, "html.parser")
    found, seen = [], set()
    for node in soup.select(".result"):
        link = node.select_one("a.result__a")
        if link is None:
            continue
        url = str(link.get("href", ""))
        if url.startswith("//"):
            url = "https:" + url
        parsed = urlparse(url)
        if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}:
            url = unquote(parse_qs(parsed.query).get("uddg", [url])[0])
            parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or url in seen:
            continue
        if normalized and not any(parsed.hostname == d or parsed.hostname.endswith("." + d) for d in normalized):
            continue
        snippet = node.select_one(".result__snippet")
        found.append(record(link.get_text(" ", strip=True)[:300], url, parsed.hostname,
                            snippet.get_text(" ", strip=True)[:4000] if snippet else ""))
        seen.add(url)
        if len(found) >= max_sources:
            break
    # Search snippets only; no hidden page downloads or model calls.
    return save_search(context, query, found, None)


@bio_function_tool(timeout=60)
async def web_search(
    ctx: RunContextWrapper[AgentRunContext],
    query: Annotated[str, Field(min_length=3, max_length=1000)],
    domains: Annotated[list[str] | None, Field(max_length=10)] = None,
    max_sources: Annotated[int, Field(ge=1, le=10)] = 5,
) -> Result[SearchResult]:
    """Search web result titles, URLs, and snippets. No full-page fetching. Return an evidence_path for evidence_retrieve or report_synthesize; unknown total is null."""
    return await invoke(ctx.context, "web_search", _operation, {"query": query, "domains": domains or [], "max_sources": max_sources}, Result[SearchResult])


__all__ = ["web_search"]
