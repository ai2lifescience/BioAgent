"""Offline smoke checks for durable knowledge ingestion and retrieval."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.infrastructure.knowledge import KnowledgeService, KnowledgePage  # noqa: E402
from tools.infrastructure.knowledge import worker  # noqa: E402
from tools.infrastructure.knowledge.crawlers import http as crawler  # noqa: E402


def main() -> int:
    page, links = crawler.extract_page(
        "https://example.org/start",
        "<html><title>Example</title><body><p>Alpha knowledge.</p><a href='/next'>Next</a><script>ignore()</script></body></html>",
        depth=0,
    )
    assert page.title == "Example"
    assert "Alpha knowledge." in page.text
    assert "ignore" not in page.text
    assert links == ["https://example.org/next"]
    assert crawler.canonical_url("https://EXAMPLE.org:443/start#fragment") == "https://example.org/start"

    with TemporaryDirectory() as directory:
        store = KnowledgeService(Path(directory) / "knowledge.sqlite3", max_workers=1)
        store.dispatch = lambda: None  # Keep this offline check in-process.
        job = store.enqueue(
            session_id="session-1", request="alpha", collection_id=None,
            seed_urls=["https://example.org/start"], allowed_domains=["example.org"],
            max_pages=2, max_depth=1, refresh=False,
        )
        assert job["status"] == "queued"
        assert store.get_job(job["job_id"], session_id="session-1")["collection_id"] == job["collection_id"]

        original_crawl, original_embed = worker.crawl, worker.embed_texts
        async def fake_crawl(**kwargs):
            return [KnowledgePage("https://example.org/start", "Example", "alpha knowledge " * 200)]
        worker.crawl = fake_crawl
        worker.embed_texts = lambda texts, **kwargs: [[1.0, 0.0] for _ in texts]
        try:
            assert worker.execute(store, job["job_id"]) == 0
        finally:
            worker.crawl, worker.embed_texts = original_crawl, original_embed
        assert store.get_job(job["job_id"], session_id="session-1")["status"] == "succeeded"
        events = store.events(job["job_id"], session_id="session-1")
        assert events[0]["event"] == "queued"
        assert events[-1]["event"] == "succeeded"
        collection = store.collection(job["collection_id"], session_id="session-1")
        assert collection["sources"] == 1 and collection["chunks"] > 0
        hits = store.retrieve(
            collection_id=job["collection_id"], session_id="session-1", question="alpha",
            query_vector=[1.0, 0.0], top_k=2,
        )
        assert hits and hits[0].record.url == "https://example.org/start"
        try:
            store.get_job(job["job_id"], session_id="other-session")
        except ValueError:
            pass
        else:
            raise AssertionError("knowledge jobs must be session-scoped")
    print("knowledge smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
