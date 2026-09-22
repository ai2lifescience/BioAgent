"""Durable collections, crawl jobs, and vector retrieval.

The local implementation uses SQLite so the service works without another
daemon.  The schema deliberately keeps collection metadata, source snapshots,
and chunks separate; replacing SQLite with Postgres/pgvector later does not
change the FunctionTool contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Lock
from uuid import uuid4

from models.config import DEFAULT_EMBEDDING_MODEL
from tools.infrastructure.tool_support.evidence_models import EvidenceRecord


TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled", "interrupted"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _source_id(collection_id: str, url: str) -> str:
    return "src_" + hashlib.sha256((collection_id + "\n" + url).encode("utf-8")).hexdigest()[:24]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KnowledgePage:
    """Normalized page produced by the crawler."""

    url: str
    title: str
    text: str
    depth: int = 0


@dataclass(frozen=True)
class KnowledgeSearchHit:
    """One chunk selected by lexical/vector retrieval."""

    score: float
    record: EvidenceRecord


class KnowledgeJobStore:
    """SQLite repository and durable dispatcher for knowledge jobs."""

    _dispatch_lock = Lock()

    def __init__(self, path: str | Path | None = None, *, max_workers: int | None = None) -> None:
        configured = path or os.getenv("AGENT_KNOWLEDGE_DB", "runtime/knowledge.sqlite3")
        self.path = Path(configured).resolve()
        self.max_workers = max(1, int(max_workers if max_workers is not None else os.getenv("AGENT_KNOWLEDGE_WORKERS", "2")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with self._db_context(write=True) as db:
            self._create_schema(db)

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        # This method is called while holding the write transaction.
        connection.executescript(
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

    def _db_context(self, *, write: bool = False):
        from contextlib import contextmanager

        @contextmanager
        def manager():
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

        return manager()

    def create_collection(self, session_id: str, name: str | None = None) -> str:
        collection_id = _id("kb")
        timestamp = _now()
        with self._db_context(write=True) as db:
            db.execute(
                "INSERT INTO collections VALUES (?, ?, ?, ?, 'empty', ?, ?)",
                (collection_id, session_id, (name or "User knowledge")[:200], DEFAULT_EMBEDDING_MODEL, timestamp, timestamp),
            )
        return collection_id

    def _assert_collection(self, db: sqlite3.Connection, collection_id: str, session_id: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM collections WHERE collection_id=? AND session_id=?", (collection_id, session_id)).fetchone()
        if row is None:
            raise ValueError("Knowledge collection was not found for this session.")
        return row

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
        with self._db_context(write=True) as db:
            if collection_id:
                self._assert_collection(db, collection_id, session_id)
            else:
                collection_id = _id("kb")
                timestamp = _now()
                db.execute(
                    "INSERT INTO collections VALUES (?, ?, ?, ?, 'empty', ?, ?)",
                    (collection_id, session_id, "User knowledge", DEFAULT_EMBEDDING_MODEL, timestamp, timestamp),
                )
            job_id, timestamp = _id("kj"), _now()
            db.execute(
                """INSERT INTO knowledge_jobs
                (job_id, collection_id, session_id, request, seed_urls, allowed_domains,
                 max_pages, max_depth, refresh, status, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)""",
                (
                    job_id, collection_id, session_id, request,
                    json.dumps(seed_urls), json.dumps(allowed_domains), max_pages,
                    max_depth, int(refresh), json.dumps({"discovered": 0, "fetched": 0, "indexed": 0, "skipped": 0}),
                    timestamp, timestamp,
                ),
            )
            self._event(db, job_id, "queued", {"job_id": job_id, "collection_id": collection_id, "status": "queued"})
        self.dispatch()
        return self.get_job(job_id, session_id=session_id)

    def job_spec(self, job_id: str) -> dict:
        """Return private worker input for one job."""
        with self._db_context() as db:
            row = self._assert_job(db, job_id, None)
            return {
                "job_id": row["job_id"], "collection_id": row["collection_id"], "session_id": row["session_id"],
                "request": row["request"], "seed_urls": json.loads(row["seed_urls"]),
                "allowed_domains": json.loads(row["allowed_domains"]), "max_pages": row["max_pages"],
                "max_depth": row["max_depth"], "refresh": bool(row["refresh"]), "status": row["status"],
            }

    def get_job(self, job_id: str, *, session_id: str | None = None) -> dict:
        self.recover()
        with self._db_context() as db:
            row = db.execute("SELECT * FROM knowledge_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None or (session_id is not None and row["session_id"] != session_id):
                raise ValueError("Knowledge job was not found.")
            return self._job_payload(row)

    def list_jobs(self, *, session_id: str, collection_id: str | None = None) -> list[dict]:
        self.recover()
        with self._db_context() as db:
            if collection_id:
                rows = db.execute("SELECT * FROM knowledge_jobs WHERE session_id=? AND collection_id=? ORDER BY created_at DESC LIMIT 100", (session_id, collection_id)).fetchall()
            else:
                rows = db.execute("SELECT * FROM knowledge_jobs WHERE session_id=? ORDER BY created_at DESC LIMIT 100", (session_id,)).fetchall()
            return [self._job_payload(row) for row in rows]

    def events(self, job_id: str, *, session_id: str, after: int = -1) -> list[dict]:
        with self._db_context() as db:
            self._assert_job(db, job_id, session_id)
            rows = db.execute(
                "SELECT sequence,event,payload,created_at FROM knowledge_job_events WHERE job_id=? AND sequence>? ORDER BY sequence",
                (job_id, after),
            ).fetchall()
            return [
                {"sequence": row["sequence"], "event": row["event"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]}
                for row in rows
            ]

    def update_progress(self, job_id: str, *, progress: dict, event: str = "progress") -> None:
        with self._db_context(write=True) as db:
            self._assert_job(db, job_id, None)
            db.execute("UPDATE knowledge_jobs SET progress=?, updated_at=? WHERE job_id=?", (json.dumps(progress), _now(), job_id))
            self._event(db, job_id, event, progress)

    def update_status(self, job_id: str, status: str, *, error: str | None = None, progress: dict | None = None) -> None:
        if status not in {"queued", "running", "indexing", *TERMINAL_JOB_STATUSES}:
            raise ValueError(f"Unsupported knowledge job status: {status}")
        with self._db_context(write=True) as db:
            self._assert_job(db, job_id, None)
            db.execute(
                "UPDATE knowledge_jobs SET status=?, progress=COALESCE(?, progress), error=?, updated_at=? WHERE job_id=?",
                (status, json.dumps(progress) if progress is not None else None, error, _now(), job_id),
            )
            self._event(db, job_id, status, {"job_id": job_id, "status": status, **(progress or {}), **({"error": error} if error else {})})

    def collection(self, collection_id: str, *, session_id: str) -> dict:
        with self._db_context() as db:
            row = self._assert_collection(db, collection_id, session_id)
            count = db.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE collection_id=?", (collection_id,)).fetchone()[0]
            sources = db.execute("SELECT COUNT(*) FROM knowledge_sources WHERE collection_id=?", (collection_id,)).fetchone()[0]
            return {"collection_id": collection_id, "status": row["status"], "sources": sources, "chunks": count, "embedding_model": row["embedding_model"], "updated_at": row["updated_at"]}

    def changed_pages(self, *, collection_id: str, session_id: str, pages: list[KnowledgePage]) -> list[KnowledgePage]:
        """Filter pages whose content hash is already present in a collection."""
        with self._db_context() as db:
            self._assert_collection(db, collection_id, session_id)
            changed: list[KnowledgePage] = []
            for page in pages:
                row = db.execute(
                    "SELECT content_hash FROM knowledge_sources WHERE collection_id=? AND canonical_url=?",
                    (collection_id, page.url),
                ).fetchone()
                if row is None or row["content_hash"] != _content_hash(page.text):
                    changed.append(page)
            return changed

    def upsert_pages(self, *, collection_id: str, session_id: str, pages: list[KnowledgePage], vectors: list[list[float]], chunk_chars: int = 1200, overlap: int = 180) -> dict[str, int]:
        if len(pages) == 0 or len(vectors) == 0:
            return {"indexed": 0, "skipped": 0, "chunks": 0}
        chunks_to_insert: list[tuple[KnowledgePage, int, str, list[float]]] = []
        vector_index = 0
        skipped = 0
        with self._db_context(write=True) as db:
            self._assert_collection(db, collection_id, session_id)
            for page in pages:
                canonical = page.url
                digest = _content_hash(page.text)
                source_id = _source_id(collection_id, canonical)
                existing = db.execute("SELECT content_hash FROM knowledge_sources WHERE collection_id=? AND canonical_url=?", (collection_id, canonical)).fetchone()
                if existing and existing["content_hash"] == digest:
                    skipped += 1
                    continue
                if existing:
                    db.execute("DELETE FROM knowledge_chunks WHERE collection_id=? AND source_id=?", (collection_id, source_id))
                    db.execute("DELETE FROM knowledge_sources WHERE collection_id=? AND source_id=?", (collection_id, source_id))
                db.execute(
                    "INSERT INTO knowledge_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (source_id, collection_id, canonical, page.title[:300], digest, _now(), page.text, json.dumps({"depth": page.depth})),
                )
                for ordinal, offset in enumerate(range(0, len(page.text), max(1, chunk_chars - overlap))):
                    excerpt = page.text[offset:offset + chunk_chars]
                    if not excerpt.strip():
                        continue
                    if vector_index >= len(vectors):
                        raise ValueError("Embedding count did not match knowledge chunks.")
                    chunks_to_insert.append((page, ordinal, excerpt, vectors[vector_index]))
                    vector_index += 1
                    if offset + chunk_chars >= len(page.text):
                        break
                for _page, ordinal, excerpt, vector in chunks_to_insert:
                    if _page is page:
                        chunk_id = f"{source_id}_c{ordinal}"
                        db.execute(
                            "INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?, ?, ?)",
                            (chunk_id, source_id, collection_id, ordinal, excerpt, json.dumps(vector, allow_nan=False)),
                        )
                chunks_to_insert = []
            if vector_index > len(vectors):
                raise ValueError("Embedding count exceeded knowledge chunks.")
            db.execute("UPDATE collections SET status='ready', updated_at=? WHERE collection_id=?", (_now(), collection_id))
        return {"indexed": len(pages) - skipped, "skipped": skipped, "chunks": vector_index}

    def retrieve(self, *, collection_id: str, session_id: str, question: str, query_vector: list[float], top_k: int) -> list[KnowledgeSearchHit]:
        import math
        import re

        with self._db_context() as db:
            self._assert_collection(db, collection_id, session_id)
            rows = db.execute(
                """SELECT c.chunk_id, c.ordinal, c.excerpt, c.vector, s.title,
                   s.canonical_url, s.fetched_at, s.source_id
                   FROM knowledge_chunks c JOIN knowledge_sources s ON s.source_id=c.source_id
                   WHERE c.collection_id=?""",
                (collection_id,),
            ).fetchall()
        terms = set(re.findall(r"\w+", question.lower()))
        def cosine(vector: list[float]) -> float:
            if len(vector) != len(query_vector) or not query_vector:
                return 0.0
            denominator = math.sqrt(sum(value * value for value in vector) * sum(value * value for value in query_vector))
            return sum(a * b for a, b in zip(vector, query_vector)) / denominator if denominator else 0.0
        scored: list[KnowledgeSearchHit] = []
        for row in rows:
            lexical_tokens = set(re.findall(r"\w+", (row["title"] + " " + row["excerpt"]).lower()))
            lexical = len(terms & lexical_tokens) / max(1, len(terms))
            score = 0.75 * cosine(json.loads(row["vector"])) + 0.25 * lexical
            record = EvidenceRecord(
                id=row["chunk_id"], title=row["title"], url=row["canonical_url"], source="knowledge",
                text=row["excerpt"], retrieved_at=row["fetched_at"],
            )
            scored.append(KnowledgeSearchHit(score=score, record=record))
        scored.sort(key=lambda item: (-item.score, item.record.id))
        return scored[:top_k]

    def dispatch(self) -> None:
        with self._dispatch_lock:
            self.recover()
            while True:
                with self._db_context(write=True) as db:
                    active = db.execute("SELECT COUNT(*) FROM knowledge_jobs WHERE status IN ('running','indexing')").fetchone()[0]
                    if active >= self.max_workers:
                        return
                    row = db.execute("SELECT job_id FROM knowledge_jobs WHERE status='queued' ORDER BY created_at, job_id LIMIT 1").fetchone()
                    if row is None:
                        return
                    job_id = row["job_id"]
                    try:
                        process = subprocess.Popen(
                            [sys.executable, "-m", "tools.infrastructure.knowledge.worker", str(self.path), job_id],
                            cwd=Path(__file__).resolve().parents[3], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"}, start_new_session=True,
                        )
                    except Exception as exc:
                        message = f"Could not start knowledge worker: {exc}"
                        db.execute("UPDATE knowledge_jobs SET status='failed', error=?, updated_at=? WHERE job_id=?", (message, _now(), job_id))
                        self._event(db, job_id, "failed", {"job_id": job_id, "status": "failed", "error": message})
                    else:
                        db.execute("UPDATE knowledge_jobs SET status='running', pid=?, updated_at=? WHERE job_id=?", (process.pid, _now(), job_id))
                        self._event(db, job_id, "started", {"job_id": job_id, "status": "running"})

    def recover(self) -> None:
        with self._db_context(write=True) as db:
            rows = db.execute("SELECT job_id,pid FROM knowledge_jobs WHERE status IN ('running','indexing')").fetchall()
            for row in rows:
                if not row["pid"] or not _pid_alive(int(row["pid"])):
                    message = "Knowledge worker exited before completion. Retry the ingestion job."
                    db.execute("UPDATE knowledge_jobs SET status='interrupted', error=?, updated_at=? WHERE job_id=?", (message, _now(), row["job_id"]))
                    self._event(db, row["job_id"], "interrupted", {"job_id": row["job_id"], "status": "interrupted", "error": message})

    @staticmethod
    def _event(db: sqlite3.Connection, job_id: str, event: str, payload: dict) -> None:
        row = db.execute("SELECT COALESCE(MAX(sequence), -1) + 1 AS next FROM knowledge_job_events WHERE job_id=?", (job_id,)).fetchone()
        db.execute("INSERT INTO knowledge_job_events VALUES (?, ?, ?, ?, ?)", (job_id, row["next"], event, json.dumps(payload, ensure_ascii=False), _now()))

    @staticmethod
    def _assert_job(db: sqlite3.Connection, job_id: str, session_id: str | None) -> sqlite3.Row:
        row = db.execute("SELECT * FROM knowledge_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or (session_id is not None and row["session_id"] != session_id):
            raise ValueError("Knowledge job was not found.")
        return row

    @staticmethod
    def _job_payload(row: sqlite3.Row) -> dict:
        return {
            "job_id": row["job_id"], "collection_id": row["collection_id"], "status": row["status"],
            "progress": json.loads(row["progress"] or "{}"), "error": row["error"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


__all__ = ["KnowledgeJobStore", "KnowledgePage", "KnowledgeSearchHit", "TERMINAL_JOB_STATUSES"]
