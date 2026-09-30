"""Bounded generic spider used only by the durable knowledge worker."""
from __future__ import annotations

import scrapy

from ..http import _allowed, canonical_url, extract_page, validate_domains
from .items import KnowledgeItem


class KnowledgeSpider(scrapy.Spider):
    name = "pipeline2agent-knowledge"
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {"tools.infrastructure.knowledge.crawlers.scrapy.middleware.PublicUrlMiddleware": 540},
        "ROBOTSTXT_OBEY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.25,
        "AUTOTHROTTLE_MAX_DELAY": 5.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_TIMEOUT": 20,
        "LOG_ENABLED": False,
        "REDIRECT_MAX_TIMES": 3,
    }

    def __init__(self, spec: dict, *args, progress=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.spec = spec
        self.domains = validate_domains(spec["allowed_domains"])
        self.seen: set[str] = set()
        self.pages = 0
        self.progress = progress or (lambda item: None)

    async def start(self):
        for request in self.start_requests():
            yield request

    def start_requests(self):
        for url in self.spec["seed_urls"]:
            yield scrapy.Request(canonical_url(url), callback=self.parse, errback=self.errback, dont_filter=True)

    def parse(self, response):
        if self.pages >= self.spec["max_pages"]:
            return
        try:
            canonical = canonical_url(response.url)
            if not _allowed(canonical, self.domains):
                self._skip(canonical, "URL is outside allowed_domains.")
                return
            depth = int(response.meta.get("depth", 0))
            page, links = extract_page(canonical, response.text, depth=depth)
        except (ValueError, AttributeError) as exc:
            self._skip(response.url, str(exc))
            return
        if page.url in self.seen:
            return
        self.seen.add(page.url)
        self.pages += 1
        yield KnowledgeItem(url=page.url, title=page.title, text=page.text, depth=page.depth)
        if self.pages >= self.spec["max_pages"] or depth >= self.spec["max_depth"]:
            return
        for link in links:
            if link not in self.seen and _allowed(link, self.domains):
                yield scrapy.Request(link, callback=self.parse, errback=self.errback)

    def errback(self, failure):
        message = failure.getErrorMessage()
        response = getattr(failure.value, "response", None)
        if response is not None:
            message = f"HTTP {response.status}: {message}"
        self._skip(failure.request.url, message)

    def _skip(self, url: str, message: str) -> None:
        self.progress({"url": url, "skipped": 1, "message": message[:300]})


__all__ = ["KnowledgeSpider"]
