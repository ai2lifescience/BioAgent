"""Regression checks for empty crawls and the supported Scrapy startup API."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from tools.infrastructure.knowledge import KnowledgePage, KnowledgeService, worker


URL = "https://example.org/record.txt"
SPEC = {"seed_urls": [URL], "allowed_domains": ["example.org"], "max_pages": 1, "max_depth": 0}


class KnowledgeWorkerTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = KnowledgeService(Path(directory.name) / "knowledge.sqlite3")
        self.store.dispatch = lambda: None

    def enqueue(self, collection_id=None):
        return self.store.enqueue(
            session_id="test", request="test record", collection_id=collection_id,
            refresh=bool(collection_id), **SPEC,
        )

    def result(self, job):
        return self.store.get_job(job["job_id"], session_id="test")

    def test_empty_crawl_fails_instead_of_reporting_success(self):
        job = self.enqueue()
        with patch.object(worker, "crawl", AsyncMock(return_value=[])), patch.object(worker, "embed_texts") as embed:
            self.assertEqual(worker.execute(self.store, job["job_id"]), 1)
        result = self.result(job)
        self.assertEqual(result["status"], "failed")
        self.assertIn("No readable pages", result["error"])
        self.assertEqual(result["progress"]["chunks"], 0)
        embed.assert_not_called()

    def test_skipped_url_and_error_survive_terminal_status(self):
        async def crawl(**kwargs):
            kwargs["progress"]({"url": URL, "skipped": 1, "message": "HTTP 404"})
            return []

        job = self.enqueue()
        with patch.object(worker, "crawl", crawl):
            self.assertEqual(worker.execute(self.store, job["job_id"]), 1)
        result = self.result(job)
        self.assertEqual(result["progress"]["skipped"], 1)
        self.assertEqual(result["progress"]["skipped_urls"], [URL])
        self.assertEqual(result["progress"]["errors"], [{"url": URL, "message": "HTTP 404"}])
        self.assertIn("HTTP 404", result["error"])

    def test_crawler_startup_error_is_reported(self):
        job = self.enqueue()
        with patch.object(worker, "crawl", AsyncMock(side_effect=ValueError("Scrapy crawl failed: startup error"))):
            self.assertEqual(worker.execute(self.store, job["job_id"]), 1)
        result = self.result(job)
        self.assertEqual(result["status"], "failed")
        self.assertIn("startup error", result["error"])

    def test_success_counts_actual_pages_even_without_progress_callbacks(self):
        job = self.enqueue()
        page = KnowledgePage(URL, "Record", "A useful annotation. " * 100)
        with patch.object(worker, "crawl", AsyncMock(return_value=[page])), patch.object(
            worker, "embed_texts", side_effect=lambda texts, **kwargs: [[1.0, 0.0] for _ in texts]
        ):
            self.assertEqual(worker.execute(self.store, job["job_id"]), 0)
        result = self.result(job)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["progress"]["fetched"], 1)
        self.assertEqual(result["progress"]["indexed"], 1)
        self.assertGreater(result["progress"]["chunks"], 0)

    def test_unchanged_refresh_succeeds_and_preserves_existing_chunks(self):
        first = self.enqueue()
        page = KnowledgePage(URL, "Record", "A useful annotation.")
        with patch.object(worker, "crawl", AsyncMock(return_value=[page])), patch.object(
            worker, "embed_texts", return_value=[[1.0, 0.0]]
        ) as embed:
            self.assertEqual(worker.execute(self.store, first["job_id"]), 0)
            embed.reset_mock()
            second = self.enqueue(first["collection_id"])
            self.assertEqual(worker.execute(self.store, second["job_id"]), 0)
            embed.assert_not_called()
        result = self.result(second)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["progress"]["fetched"], 1)
        self.assertEqual(result["progress"]["indexed"], 0)
        self.assertEqual(result["progress"]["skipped"], 1)
        self.assertEqual(self.store.collection(first["collection_id"], session_id="test")["chunks"], 1)


@unittest.skipUnless(importlib.util.find_spec("scrapy"), "optional Scrapy is not installed")
class ScrapyStartupTests(unittest.TestCase):
    def test_async_start_yields_the_seed_at_depth_zero(self):
        from tools.infrastructure.knowledge.crawlers.scrapy.spider import KnowledgeSpider

        async def seeds():
            return [request async for request in KnowledgeSpider(SPEC).start()]

        requests = asyncio.run(seeds())
        self.assertEqual([request.url for request in requests], [URL])
        self.assertTrue(requests[0].dont_filter)

    def test_parse_indexes_seed_without_following_links_at_depth_zero(self):
        from scrapy import Request
        from scrapy.http import HtmlResponse
        from tools.infrastructure.knowledge.crawlers.scrapy.spider import KnowledgeSpider

        spider = KnowledgeSpider(SPEC)
        response = HtmlResponse(URL, body=b"<p>Record</p><a href='/next'>Next</a>", encoding="utf-8", request=Request(URL))
        items = list(spider.parse(response))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], URL)
        self.assertEqual(items[0]["depth"], 0)
        self.assertEqual(list(spider.parse(response)), [])

    def test_request_failure_emits_a_skipped_url(self):
        from scrapy import Request
        from twisted.python.failure import Failure
        from tools.infrastructure.knowledge.crawlers.scrapy.spider import KnowledgeSpider

        events = []
        failure = Failure(ValueError("download refused"))
        failure.request = Request(URL)
        KnowledgeSpider(SPEC, progress=events.append).errback(failure)
        self.assertEqual(events, [{"url": URL, "skipped": 1, "message": "download refused"}])

    def test_runner_does_not_report_completion_after_startup_failure(self):
        from twisted.internet.defer import fail
        from tools.infrastructure.knowledge.crawlers.scrapy import runner

        output = io.StringIO()
        with patch("scrapy.crawler.CrawlerProcess") as process, patch("sys.stdin", io.StringIO(json.dumps(SPEC))), patch("sys.stdout", output):
            process.return_value.crawl.return_value = fail(RuntimeError("startup broke"))
            self.assertEqual(runner.main(), 1)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(messages, [{"type": "error", "message": "startup broke"}])

    def test_http_error_includes_status_code(self):
        from scrapy import Request
        from scrapy.http import Response
        from scrapy.spidermiddlewares.httperror import HttpError
        from twisted.python.failure import Failure
        from tools.infrastructure.knowledge.crawlers.scrapy.spider import KnowledgeSpider

        events = []
        failure = Failure(HttpError(Response(URL, status=404), "Ignoring non-200 response"))
        failure.request = Request(URL)
        KnowledgeSpider(SPEC, progress=events.append).errback(failure)
        self.assertEqual(events[0]["message"], "HTTP 404: Ignoring non-200 response")


if __name__ == "__main__":
    unittest.main()
