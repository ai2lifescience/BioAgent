"""SQLite persistence for the durable knowledge service.

This module deliberately contains no crawling, embedding, or worker-process
logic.  It is the replaceable persistence boundary for local development;
another deployment can provide the same small repository contract with
Postgres/pgvector.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

from models.config import DEFAULT_EMBEDDING_MODEL

from .models import KnowledgePage, content_hash, new_id, now, source_id


class KnowledgeRepository:
    """Persist collections, source snapshots, chunks, and job events."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("AGENT_KNOWLEDGE_DB", "runtime/knowledge.sqlite3")
        self.path = Path(configured).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with self._db_context(write=True) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    collection_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    source_id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    text TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    UNIQUE(collection_id, canonical_url),
                    FOREIGN KEY(collection_id) REFERENCES collections(collection_id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    excerpt TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id),
                    FOREIGN KEY(collection_id) REFERENCES collections(collection_id)
                );
                CREATE INDEX IF NOT EXISTS chunks_by_collection ON knowledge_chunks(collection_id);
                CREATE TABLE IF NOT EXISTS knowledge_jobs (
                    job_id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request TEXT NOT NULL,
                    seed_urls TEXT NOT NULL,
                    allowed_domains TEXT NOT NULL,
                    max_pages INTEGER NOT NULL,
                    max_depth INTEGER NOT NULL,
                    refresh INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    progress TEXT NOT NULL,
                    error TEXT,
                    pid INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(collection_id) REFERENCES collections(collection_id)
                );
                CREATE INDEX IF NOT EXISTS jobs_by_session ON knowledge_jobs(session_id, created_at);
                CREATE TABLE IF NOT EXISTS knowledge_job_events (
                    job_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(job_id, sequence),
                    FOREIGN KEY(job_id) REFERENCES knowledge_jobs(job_id)
                );
                """
            )

    @contextmanager
    def _db_context(self, *, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=60)
        connection.row_factory = sqlite3.Row
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_collection(self, session_id: str, name: str | None = None) -> str:
        collection_id = new_id("kb")
        timestamp = now()
        with self._db_context(write=True) as db:
            db.execute(
                "INSERT INTO collections VALUES (?, ?, ?, ?, 'empty', ?, ?)",
                (collection_id, session_id, (name or "User knowledge")[:200], DEFAULT_EMBEDDING_MODEL, timestamp, timestamp),
            )
        return collection_id

    def _assert_collection(self, db: sqlite3.Connection, collection_id: str, session_id: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM collections WHERE collection_id=? AND session_id=?",
            (collection_id, session_id),
        ).fetchone()
        if row is None:
            raise ValueError("Knowledge collection was not found for this session.")
        return row

    def get_collection(self, collection_id: str, *, session_id: str) -> dict:
        with self._db_context() as db:
            row = self._assert_collection(db, collection_id, session_id)
            chunks = db.execute(
                "SELECT COUNT(*) FROM knowledge_chunks WHERE collection_id=?", (collection_id,)
            ).fetchone()[0]
            sources = db.execute(
                "SELECT COUNT(*) FROM knowledge_sources WHERE collection_id=?", (collection_id,)
            ).fetchone()[0]
            return {
                "collection_id": collection_id,
                "status": row["status"],
                "sources": sources,
                "chunks": chunks,
                "embedding_model": row["embedding_model"],
                "updated_at": row["updated_at"],
            }

    def create_job(
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
    ) -> str:
        with self._db_context(write=True) as db:
            if collection_id:
                self._assert_collection(db, collection_id, session_id)
            else:
                collection_id = new_id("kb")
                timestamp = now()
                db.execute(
                    "INSERT INTO collections VALUES (?, ?, ?, ?, 'empty', ?, ?)",
                    (collection_id, session_id, "User knowledge", DEFAULT_EMBEDDING_MODEL, timestamp, timestamp),
                )
            job_id, timestamp = new_id("kj"), now()
            db.execute(
                """INSERT INTO knowledge_jobs
                (job_id, collection_id, session_id, request, seed_urls, allowed_domains,
                 max_pages, max_depth, refresh, status, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)""",
                (
                    job_id,
                    collection_id,
                    session_id,
                    request,
                    json.dumps(seed_urls),
                    json.dumps(allowed_domains),
                    max_pages,
                    max_depth,
                    int(refresh),
                    json.dumps({"discovered": 0, "fetched": 0, "indexed": 0, "skipped": 0}),
                    timestamp,
                    timestamp,
                ),
            )
            self._event(db, job_id, "queued", {"job_id": job_id, "collection_id": collection_id, "status": "queued"})
        return job_id

    def get_job_row(self, job_id: str, *, session_id: str | None = None) -> sqlite3.Row:
        with self._db_context() as db:
            return self._assert_job(db, job_id, session_id)

    def job_spec(self, job_id: str) -> dict:
        row = self.get_job_row(job_id)
        return {
            "job_id": row["job_id"],
            "collection_id": row["collection_id"],
            "session_id": row["session_id"],
            "request": row["request"],
            "seed_urls": json.loads(row["seed_urls"]),
            "allowed_domains": json.loads(row["allowed_domains"]),
            "max_pages": row["max_pages"],
            "max_depth": row["max_depth"],
            "refresh": bool(row["refresh"]),
            "status": row["status"],
        }

    def list_job_rows(self, *, session_id: str, collection_id: str | None = None) -> list[sqlite3.Row]:
        with self._db_context() as db:
            if collection_id:
                return db.execute(
                    "SELECT * FROM knowledge_jobs WHERE session_id=? AND collection_id=? ORDER BY created_at DESC LIMIT 100",
                    (session_id, collection_id),
                ).fetchall()
            return db.execute(
                "SELECT * FROM knowledge_jobs WHERE session_id=? ORDER BY created_at DESC LIMIT 100",
                (session_id,),
            ).fetchall()

    @staticmethod
    def job_payload(row: sqlite3.Row) -> dict:
        return {
            "job_id": row["job_id"],
            "collection_id": row["collection_id"],
            "status": row["status"],
            "progress": json.loads(row["progress"] or "{}"),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def event_rows(self, job_id: str, *, session_id: str, after: int = -1) -> list[sqlite3.Row]:
        with self._db_context() as db:
            self._assert_job(db, job_id, session_id)
            return db.execute(
                "SELECT sequence,event,payload,created_at FROM knowledge_job_events WHERE job_id=? AND sequence>? ORDER BY sequence",
                (job_id, after),
            ).fetchall()

    def update_progress(self, job_id: str, *, progress: dict, event: str = "progress") -> None:
        with self._db_context(write=True) as db:
            self._assert_job(db, job_id, None)
            db.execute(
                "UPDATE knowledge_jobs SET progress=?, updated_at=? WHERE job_id=?",
                (json.dumps(progress), now(), job_id),
            )
            self._event(db, job_id, event, progress)

    def update_status(self, job_id: str, status: str, *, terminal_statuses: frozenset[str], error: str | None = None, progress: dict | None = None) -> None:
        if status not in {"queued", "running", "indexing", *terminal_statuses}:
            raise ValueError(f"Unsupported knowledge job status: {status}")
        with self._db_context(write=True) as db:
            self._assert_job(db, job_id, None)
            db.execute(
                "UPDATE knowledge_jobs SET status=?, progress=COALESCE(?, progress), error=?, updated_at=? WHERE job_id=?",
                (status, json.dumps(progress) if progress is not None else None, error, now(), job_id),
            )
            self._event(
                db,
                job_id,
                status,
                {"job_id": job_id, "status": status, **(progress or {}), **({"error": error} if error else {})},
            )

    def dispatch_next(self, max_workers: int, launch: Callable[[str], int]) -> bool:
        """Serialize selection and launch across server and worker processes.

        The child reads its job only after this write transaction commits, so
        it cannot race the parent recording its PID and running status.
        """
        with self._db_context(write=True) as db:
            active = db.execute(
                "SELECT COUNT(*) FROM knowledge_jobs WHERE status IN ('running','indexing')"
            ).fetchone()[0]
            if active >= max_workers:
                return False
            row = db.execute(
                "SELECT job_id FROM knowledge_jobs WHERE status='queued' ORDER BY created_at, job_id LIMIT 1"
            ).fetchone()
            if row is None:
                return False
            job_id = row["job_id"]
            try:
                pid = launch(job_id)
            except Exception:
                message = "Could not start knowledge worker. Check server logs and worker configuration."
                db.execute(
                    "UPDATE knowledge_jobs SET status='failed', error=?, updated_at=? WHERE job_id=?",
                    (message, now(), job_id),
                )
                self._event(db, job_id, "failed", {"job_id": job_id, "status": "failed", "error": message})
            else:
                db.execute(
                    "UPDATE knowledge_jobs SET status='running', pid=?, updated_at=? WHERE job_id=?",
                    (pid, now(), job_id),
                )
                self._event(db, job_id, "started", {"job_id": job_id, "status": "running"})
            return True

    def recover_jobs(self, is_alive: Callable[[int], bool]) -> None:
        with self._db_context(write=True) as db:
            rows = db.execute(
                "SELECT job_id,pid FROM knowledge_jobs WHERE status IN ('running','indexing')"
            ).fetchall()
            for row in rows:
                if row["pid"] and is_alive(int(row["pid"])):
                    continue
                message = "Knowledge worker exited before completion. Retry the ingestion job."
                db.execute(
                    "UPDATE knowledge_jobs SET status='interrupted', error=?, updated_at=? WHERE job_id=?",
                    (message, now(), row["job_id"]),
                )
                self._event(db, row["job_id"], "interrupted", {
                    "job_id": row["job_id"], "status": "interrupted", "error": message,
                })

    def changed_pages(self, *, collection_id: str, session_id: str, pages: list[KnowledgePage]) -> list[KnowledgePage]:
        with self._db_context() as db:
            self._assert_collection(db, collection_id, session_id)
            changed: list[KnowledgePage] = []
            for page in pages:
                row = db.execute(
                    "SELECT content_hash FROM knowledge_sources WHERE collection_id=? AND canonical_url=?",
                    (collection_id, page.url),
                ).fetchone()
                if row is None or row["content_hash"] != content_hash(page.text):
                    changed.append(page)
            return changed

    def replace_pages(
        self,
        *,
        collection_id: str,
        session_id: str,
        pages: list[KnowledgePage],
        page_chunks: list[list[tuple[str, list[float]]]],
    ) -> dict[str, int]:
        if len(pages) != len(page_chunks):
            raise ValueError("Knowledge page and chunk counts did not match.")
        skipped = 0
        indexed = 0
        chunk_count = 0
        with self._db_context(write=True) as db:
            self._assert_collection(db, collection_id, session_id)
            for page, chunks in zip(pages, page_chunks):
                digest = content_hash(page.text)
                canonical = page.url
                current = db.execute(
                    "SELECT content_hash FROM knowledge_sources WHERE collection_id=? AND canonical_url=?",
                    (collection_id, canonical),
                ).fetchone()
                if current and current["content_hash"] == digest:
                    skipped += 1
                    continue
                source = source_id(collection_id, canonical)
                db.execute("DELETE FROM knowledge_chunks WHERE collection_id=? AND source_id=?", (collection_id, source))
                db.execute("DELETE FROM knowledge_sources WHERE collection_id=? AND source_id=?", (collection_id, source))
                db.execute(
                    "INSERT INTO knowledge_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (source, collection_id, canonical, page.title[:300], digest, now(), page.text, json.dumps({"depth": page.depth})),
                )
                for ordinal, (excerpt, vector) in enumerate(chunks):
                    chunk_id = f"{source}_c{ordinal}"
                    db.execute(
                        "INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?, ?, ?)",
                        (chunk_id, source, collection_id, ordinal, excerpt, json.dumps(vector, allow_nan=False)),
                    )
                    chunk_count += 1
                indexed += 1
            if indexed:
                db.execute("UPDATE collections SET status='ready', updated_at=? WHERE collection_id=?", (now(), collection_id))
        return {"indexed": indexed, "skipped": skipped, "chunks": chunk_count}

    def chunk_rows(self, *, collection_id: str, session_id: str) -> list[sqlite3.Row]:
        with self._db_context() as db:
            self._assert_collection(db, collection_id, session_id)
            return db.execute(
                """SELECT c.chunk_id, c.ordinal, c.excerpt, c.vector, s.title,
                   s.canonical_url, s.fetched_at, s.source_id
                   FROM knowledge_chunks c JOIN knowledge_sources s ON s.source_id=c.source_id
                   WHERE c.collection_id=?""",
                (collection_id,),
            ).fetchall()

    @staticmethod
    def _event(db: sqlite3.Connection, job_id: str, event: str, payload: dict) -> None:
        row = db.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 AS next FROM knowledge_job_events WHERE job_id=?",
            (job_id,),
        ).fetchone()
        db.execute(
            "INSERT INTO knowledge_job_events VALUES (?, ?, ?, ?, ?)",
            (job_id, row["next"], event, json.dumps(payload, ensure_ascii=False), now()),
        )

    @staticmethod
    def _assert_job(db: sqlite3.Connection, job_id: str, session_id: str | None) -> sqlite3.Row:
        row = db.execute("SELECT * FROM knowledge_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or (session_id is not None and row["session_id"] != session_id):
            raise ValueError("Knowledge job was not found.")
        return row


__all__ = ["KnowledgeRepository"]
