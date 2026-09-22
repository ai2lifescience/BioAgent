"""Durable queue and detached worker dispatch for knowledge ingestion."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock

from .models import TERMINAL_JOB_STATUSES
from .repository import KnowledgeRepository


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


class KnowledgeJobQueue:
    """Queue knowledge work and run it in restartable worker processes."""

    _dispatch_lock = Lock()

    def __init__(self, repository: KnowledgeRepository, *, max_workers: int | None = None) -> None:
        self.repository = repository
        self.max_workers = max(
            1,
            int(max_workers if max_workers is not None else os.getenv("AGENT_KNOWLEDGE_WORKERS", "2")),
        )

    @property
    def path(self) -> Path:
        return self.repository.path

    def enqueue(self, **kwargs) -> dict:
        job_id = self.repository.create_job(**kwargs)
        self.dispatch()
        return self.get_job(job_id, session_id=kwargs["session_id"])

    def job_spec(self, job_id: str) -> dict:
        return self.repository.job_spec(job_id)

    def get_job(self, job_id: str, *, session_id: str | None = None) -> dict:
        self.recover()
        return self.repository.job_payload(self.repository.get_job_row(job_id, session_id=session_id))

    def list_jobs(self, *, session_id: str, collection_id: str | None = None) -> list[dict]:
        self.recover()
        return [
            self.repository.job_payload(row)
            for row in self.repository.list_job_rows(session_id=session_id, collection_id=collection_id)
        ]

    def events(self, job_id: str, *, session_id: str, after: int = -1) -> list[dict]:
        return [
            {
                "sequence": row["sequence"],
                "event": row["event"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in self.repository.event_rows(job_id, session_id=session_id, after=after)
        ]

    def update_progress(self, *args, **kwargs) -> None:
        self.repository.update_progress(*args, **kwargs)

    def update_status(self, job_id: str, status: str, *, error: str | None = None, progress: dict | None = None) -> None:
        self.repository.update_status(
            job_id,
            status,
            terminal_statuses=TERMINAL_JOB_STATUSES,
            error=error,
            progress=progress,
        )

    def dispatch(self) -> None:
        with self._dispatch_lock:
            self.recover()
            while self.repository.dispatch_next(self.max_workers, self._launch):
                pass

    def _launch(self, job_id: str) -> int:
        process = subprocess.Popen(
            [sys.executable, "-m", "tools.infrastructure.knowledge.worker", str(self.path), job_id],
            cwd=Path(__file__).resolve().parents[3],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            start_new_session=True,
        )
        return process.pid

    def recover(self) -> None:
        self.repository.recover_jobs(_pid_alive)


__all__ = ["KnowledgeJobQueue"]
