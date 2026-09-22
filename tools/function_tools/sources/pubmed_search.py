"""Self-contained SDK capability: pubmed_search."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import xml.etree.ElementTree as ET
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


async def _operation(*, query: str, max_records: int, context):
    params = {"db": "pubmed", "tool": "Pipeline2Agent"}
    if os.getenv("NCBI_EMAIL"):
        params["email"] = os.environ["NCBI_EMAIL"]
    if os.getenv("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        payload = json.loads(await request(f"{base}/esearch.fcgi", {**params, "term": query, "retmode": "json", "retmax": max_records, "sort": "relevance"}))
        search = payload["esearchresult"]
        if search.get("ERROR"):
            raise ValueError(search["ERROR"])
        ids = search.get("idlist", [])
        records = []
        if ids:
            xml = await request(f"{base}/efetch.fcgi", {**params, "id": ",".join(ids), "retmode": "xml"})
            root = ET.fromstring(xml)
            for article in root.findall(".//PubmedArticle"):
                pmid = article.findtext(".//PMID")
                title = " ".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else ""
                abstract = "\n".join(" ".join(node.itertext()) for node in article.findall(".//AbstractText"))
                if pmid and (title or abstract):
                    records.append(record(title or f"PubMed {pmid}", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "PubMed", title + "\n" + abstract,
                                          pmid=pmid, year=article.findtext(".//PubDate/Year")))
        return save_search(context, query, records, int(search.get("count", len(records))))
    except httpx2.HTTPError:
        # HTTP exception URLs can include the host-owned NCBI API key.
        raise RuntimeError("PubMed request failed; retry later.") from None


@bio_function_tool(timeout=60)
async def pubmed_search(
    ctx: RunContextWrapper[AgentRunContext],
    query: Annotated[str, Field(min_length=1, max_length=2000)],
    max_records: Annotated[int, Field(ge=1, le=20)] = 6,
) -> Result[SearchResult]:
    """Search PubMed by query and fetch matching abstracts. Return a bounded preview and an evidence_path for evidence_retrieve or report_synthesize."""
    return await invoke(ctx.context, "pubmed_search", _operation, {"query": query, "max_records": max_records}, Result[SearchResult])


__all__ = ["pubmed_search"]
