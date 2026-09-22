"""Application boundary for knowledge ingestion, status, and retrieval."""
from __future__ import annotations

from pathlib import Path

from .indexer import KnowledgeIndexer
from .jobs import KnowledgeJobQueue
from .models import KnowledgeSearchHit
from .repository import KnowledgeRepository


class KnowledgeService:
    """Compose persistence, job lifecycle, and indexing behind the SDK tools."""

    def __init__(self, path: str | Path | None = None, *, max_workers: int | None = None) -> None:
        self.repository = KnowledgeRepository(path)
        self.jobs = KnowledgeJobQueue(self.repository, max_workers=max_workers)
        self.indexer = KnowledgeIndexer(self.repository)

    def enqueue(
        self,
        *,
        session_id: str,
        request: str,
        collection_id: str | None,
        seed_urls: list[str],
        allowed_domains: list[str],
        max_pages: int,
        max_depth: int,
        refresh: bool,
    ) -> dict:
        job_id = self.repository.create_job(
            session_id=session_id, request=request, collection_id=collection_id,
            seed_urls=seed_urls, allowed_domains=allowed_domains,
            max_pages=max_pages, max_depth=max_depth, refresh=refresh,
        )
        self.dispatch()
        return self.jobs.get_job(job_id, session_id=session_id)

    def dispatch(self) -> None:
        self.jobs.dispatch()

    @property
    def path(self) -> Path:
        return self.jobs.path

    @property
    def max_workers(self) -> int:
        return self.jobs.max_workers

    def job_spec(self, job_id: str) -> dict:
        return self.jobs.job_spec(job_id)

    def get_job(self, job_id: str, *, session_id: str) -> dict:
        self.repository.get_job_row(job_id, session_id=session_id)
        self.dispatch()
        return self.jobs.get_job(job_id, session_id=session_id)

    def events(self, job_id: str, *, session_id: str, after: int = -1) -> list[dict]:
        self.repository.get_job_row(job_id, session_id=session_id)
        self.dispatch()
        return self.jobs.events(job_id, session_id=session_id, after=after)

    def list_jobs(self, *, session_id: str, collection_id: str | None = None) -> list[dict]:
        return self.jobs.list_jobs(session_id=session_id, collection_id=collection_id)

    def update_progress(self, job_id: str, *, progress: dict, event: str = "progress") -> None:
        self.jobs.update_progress(job_id, progress=progress, event=event)

    def update_status(self, job_id: str, status: str, *, error: str | None = None, progress: dict | None = None) -> None:
        self.jobs.update_status(job_id, status, error=error, progress=progress)

    def collection(self, collection_id: str, *, session_id: str) -> dict:
        return self.repository.get_collection(collection_id, session_id=session_id)

    def changed_pages(self, *, collection_id: str, session_id: str, pages):
        return self.indexer.changed_pages(collection_id=collection_id, session_id=session_id, pages=pages)

    def upsert_pages(self, *, collection_id: str, session_id: str, pages, vectors, chunk_chars=1200, overlap=180):
        return self.indexer.index(
            collection_id=collection_id, session_id=session_id, pages=pages, vectors=vectors,
            chunk_chars=chunk_chars, overlap=overlap,
        )

    def retrieve(
        self, *, collection_id: str, session_id: str, question: str,
        query_vector: list[float], top_k: int,
    ) -> list[KnowledgeSearchHit]:
        return self.indexer.retrieve(
            collection_id=collection_id, session_id=session_id,
            question=question, query_vector=query_vector, top_k=top_k,
        )


__all__ = ["KnowledgeService"]
