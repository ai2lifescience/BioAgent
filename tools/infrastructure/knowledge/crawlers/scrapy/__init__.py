"""Run optional Scrapy in an isolated process, outside the SDK event loop."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from ..http import _allowed, canonical_url, discover, validate_domains
from ..protocol import CrawlRequest, ProgressCallback
from ...models import KnowledgePage


class ScrapyCrawler:
    async def crawl(self, request: CrawlRequest, progress: ProgressCallback | None = None) -> list[KnowledgePage]:
        domains = validate_domains(request.allowed_domains)
        seeds = list(dict.fromkeys(canonical_url(url) for url in request.seed_urls))
        if domains and any(not _allowed(url, domains) for url in seeds):
            raise ValueError("Every seed URL must match allowed_domains.")
        if not seeds:
            seeds = await discover(request.request, domains, min(request.max_pages, 10))
        if not seeds:
            raise ValueError("No public sources were discovered for the request.")
        if not domains:
            domains = sorted({urlparse(url).hostname for url in seeds})
        spec = asdict(request)
        spec.update(seed_urls=seeds, allowed_domains=domains)
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tools.infrastructure.knowledge.crawlers.scrapy.runner",
            cwd=Path(__file__).resolve().parents[5],
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            # Diagnostics stay on the host; stdout is the document/event protocol.
            stderr=None, limit=1024 * 1024,
        )
        pages: list[KnowledgePage] = []
        try:
            async with asyncio.timeout(600):
                process.stdin.write(json.dumps(spec).encode() + b"\n")
                await process.stdin.drain()
                process.stdin.close()
                complete = False
                async for line in process.stdout:
                    item = json.loads(line)
                    if item["type"] == "page":
                        pages.append(KnowledgePage(**item["page"]))
                    elif item["type"] == "progress" and progress:
                        progress(item["progress"])
                    elif item["type"] == "complete":
                        complete = True
                code = await process.wait()
                if code or not complete:
                    raise ValueError("Scrapy crawl failed. Check the worker logs.")
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        return pages
