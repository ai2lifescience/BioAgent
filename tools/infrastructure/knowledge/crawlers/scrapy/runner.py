"""Subprocess entry point for one optional Scrapy crawl."""
from __future__ import annotations

import json
import sys

from .spider import KnowledgeSpider


def main() -> int:
    spec = json.loads(sys.stdin.readline())
    from scrapy import signals
    from scrapy.crawler import CrawlerProcess

    count = 0
    errors: list[str] = []

    def progress(value: dict) -> None:
        print(json.dumps({"type": "progress", "progress": value}), flush=True)

    def collect_item(item, response, spider) -> None:
        nonlocal count
        value = {key: item[key] for key in ("url", "title", "text", "depth")}
        count += 1
        print(json.dumps({"type": "page", "page": value}), flush=True)
        progress({"url": value["url"], "fetched": count, "depth": value["depth"]})

    def spider_error(failure, response, spider) -> None:
        progress({"url": response.url, "skipped": 1, "message": failure.getErrorMessage()[:300]})

    def crawl_error(failure) -> None:
        errors.append(failure.getErrorMessage()[:1000])

    settings = {
        "ROBOTSTXT_OBEY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.25,
        "AUTOTHROTTLE_MAX_DELAY": 5.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_TIMEOUT": 20,
        "LOG_ENABLED": False,
        "REDIRECT_MAX_TIMES": 3,
    }
    process = CrawlerProcess(settings=settings)
    crawler = process.create_crawler(KnowledgeSpider)
    crawler.signals.connect(collect_item, signal=signals.item_scraped, weak=False)
    crawler.signals.connect(spider_error, signal=signals.spider_error, weak=False)
    process.crawl(crawler, spec=spec, progress=progress).addErrback(crawl_error)
    process.start()
    if errors:
        print(json.dumps({"type": "error", "message": "; ".join(errors)}), flush=True)
        return 1
    print(json.dumps({"type": "complete", "count": count}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
