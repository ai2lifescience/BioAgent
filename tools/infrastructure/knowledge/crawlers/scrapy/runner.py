"""Subprocess entry point for one optional Scrapy crawl."""
from __future__ import annotations

import json
import sys

from .items import KnowledgeItem
from .spider import KnowledgeSpider


def main() -> int:
    spec = json.loads(sys.stdin.readline())
    from scrapy.crawler import CrawlerProcess

    collected: list[dict] = []

    class CollectPipeline:
        def process_item(self, item: KnowledgeItem, spider):
            value = {key: item[key] for key in ("url", "title", "text", "depth")}
            collected.append(value)
            return item

    settings = {
        "ITEM_PIPELINES": {"__main__.CollectPipeline": 100},
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
    process.crawl(KnowledgeSpider, spec=spec)
    process.start()
    for page in collected:
        print(json.dumps({"type": "page", "page": page}), flush=True)
    print(json.dumps({"type": "complete", "count": len(collected)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
