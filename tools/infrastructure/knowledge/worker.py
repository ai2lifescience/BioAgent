"""Detached worker for one durable knowledge ingestion job."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from tools.infrastructure.tool_support.embeddings import embed_texts

from .crawlers import crawl
from .service import KnowledgeService


def execute(store: KnowledgeService, job_id: str) -> int:
    spec = store.jobs.job_spec(job_id)
    if spec["status"] not in {"queued", "running", "indexing"}:
        return 0
    try:
        progress = {"discovered": 0, "fetched": 0, "indexed": 0, "skipped": 0}

        def on_progress(item: dict) -> None:
            if item.get("fetched"):
                progress["fetched"] = int(item["fetched"])
            if item.get("skipped"):
                progress["skipped"] += int(item["skipped"])
            if item.get("url"):
                progress["last_url"] = str(item["url"])
            store.jobs.update_progress(job_id, progress=progress)

        pages = asyncio.run(
            crawl(
                request=spec["request"], seed_urls=spec["seed_urls"],
                allowed_domains=spec["allowed_domains"], max_pages=spec["max_pages"],
                max_depth=spec["max_depth"], progress=on_progress,
            )
        )
        progress["discovered"] = len(pages)
        changed = store.indexer.changed_pages(collection_id=spec["collection_id"], session_id=spec["session_id"], pages=pages)
        progress["skipped"] += len(pages) - len(changed)
        store.jobs.update_status(job_id, "indexing", progress=progress)
        collection = store.collection(spec["collection_id"], session_id=spec["session_id"])
        chunk_texts = store.indexer.chunk_texts(changed)
        vectors: list[list[float]] = []
        for start in range(0, len(chunk_texts), 64):
            vectors.extend(embed_texts(chunk_texts[start:start + 64], model=collection["embedding_model"]))
        indexed = store.indexer.index(
            collection_id=spec["collection_id"], session_id=spec["session_id"],
            pages=changed, vectors=vectors,
        )
        progress.update(indexed=indexed["indexed"], skipped=progress["skipped"] + indexed["skipped"], chunks=indexed["chunks"])
        store.jobs.update_status(job_id, "succeeded", progress=progress)
        return 0
    except Exception as exc:
        store.jobs.update_status(job_id, "failed", error=str(exc)[:1000])
        return 1
    finally:
        store.dispatch()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("job_id")
    args = parser.parse_args(argv)
    return execute(KnowledgeService(Path(args.database)), args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["execute", "main"]
