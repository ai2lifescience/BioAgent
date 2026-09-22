"""Select a private crawler implementation without importing Scrapy eagerly."""
from __future__ import annotations

from dataclasses import asdict
from importlib.util import find_spec
import os

from .protocol import Crawler, CrawlRequest, ProgressCallback
from ..models import KnowledgePage


class HttpCrawler:
    async def crawl(self, request: CrawlRequest, progress: ProgressCallback | None = None) -> list[KnowledgePage]:
        from .http import crawl

        return await crawl(**asdict(request), progress=progress)


def get_crawler(backend: str | None = None) -> Crawler:
    selected = (backend or os.getenv("AGENT_KNOWLEDGE_CRAWLER", "auto")).strip().lower()
    if selected not in {"auto", "http", "scrapy"}:
        raise ValueError("AGENT_KNOWLEDGE_CRAWLER must be auto, http, or scrapy.")
    if selected == "http" or (selected == "auto" and find_spec("scrapy") is None):
        return HttpCrawler()
    if find_spec("scrapy") is None:
        raise ValueError("Scrapy is not installed. Install requirements.txt or choose the http crawler.")
    from .scrapy import ScrapyCrawler

    return ScrapyCrawler()


async def crawl(*, request: str, seed_urls: list[str], allowed_domains: list[str], max_pages: int, max_depth: int, progress: ProgressCallback | None = None) -> list[KnowledgePage]:
    spec = CrawlRequest(request, seed_urls, allowed_domains, max_pages, max_depth)
    return await get_crawler().crawl(spec, progress)


__all__ = ["CrawlRequest", "Crawler", "crawl", "get_crawler"]
