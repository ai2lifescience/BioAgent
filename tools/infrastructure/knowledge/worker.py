"""Detached worker for one durable knowledge ingestion job."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from tools.infrastructure.tool_support.embeddings import embed_texts

from .crawler import crawl
from .store import KnowledgeJobStore, KnowledgePage


CHUNK_CHARS = 1200
CHUNK_OVERLAP = 180


def _chunks(pages: list[KnowledgePage]) -> list[str]:
    values: list[str] = []
    for page in pages:
        for offset in range(0, len(page.text), max(1, CHUNK_CHARS - CHUNK_OVERLAP)):
            excerpt = page.text[offset:offset + CHUNK_CHARS]
            if excerpt.strip():
                values.append(excerpt)
            if offset + CHUNK_CHARS >= len(page.text):
                break
    return values


def execute(store: KnowledgeJobStore, job_id: str) -> int:
    spec = store.job_spec(job_id)
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
            store.update_progress(job_id, progress=progress)

        pages = asyncio.run(
            crawl(
                request=spec["request"], seed_urls=spec["seed_urls"],
                allowed_domains=spec["allowed_domains"], max_pages=spec["max_pages"],
                max_depth=spec["max_depth"], progress=on_progress,
            )
        )
        progress["discovered"] = len(pages)
        changed = store.changed_pages(collection_id=spec["collection_id"], session_id=spec["session_id"], pages=pages)
        progress["skipped"] += len(pages) - len(changed)
        store.update_status(job_id, "indexing", progress=progress)
        chunk_texts = _chunks(changed)
        vectors: list[list[float]] = []
        for start in range(0, len(chunk_texts), 64):
            vectors.extend(embed_texts(chunk_texts[start:start + 64]))
        indexed = store.upsert_pages(
            collection_id=spec["collection_id"], session_id=spec["session_id"],
            pages=changed, vectors=vectors, chunk_chars=CHUNK_CHARS, overlap=CHUNK_OVERLAP,
        )
        progress.update(indexed=indexed["indexed"], skipped=progress["skipped"] + indexed["skipped"], chunks=indexed["chunks"])
        store.update_status(job_id, "succeeded", progress=progress)
        return 0
    except Exception as exc:
        store.update_status(job_id, "failed", error=str(exc)[:1000])
        return 1
    finally:
        store.dispatch()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("job_id")
    args = parser.parse_args(argv)
    return execute(KnowledgeJobStore(Path(args.database)), args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["execute", "main"]
