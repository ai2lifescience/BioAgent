"""SQLite job state, private to one persistent session workspace."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "timed_out"}
PIPELINE_RUN_ROOT = "runtime/agent_runs"
PIPELINE_STATE_ROOT = f"{PIPELINE_RUN_ROOT}/.pipeline"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def confined(root: Path, value: str | Path) -> Path:
    """Resolve a relative public path, rejecting traversal and symlink escapes."""
    path = Path(value)
    if path.is_absolute() or not path.parts or any(p in {"..", "."} or p.startswith(".") for p in path.parts):
        raise ValueError("Paths must be visible files relative to the session workspace.")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Path escapes the session workspace.")
    return resolved


def atomic_json(path: Path, value: dict | list) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class JobStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        private = self.root / PIPELINE_STATE_ROOT
        if private.is_symlink():
            raise ValueError("Pipeline state directory cannot be a symlink.")
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = private / "jobs.sqlite3"
        if self.database.is_symlink():
            raise ValueError("Pipeline database cannot be a symlink.")
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.database, timeout=30)
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    def directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job or plan ID.")
        return confined(self.root, f"{PIPELINE_RUN_ROOT}/{job_id}")

    def create(self, plan: dict) -> dict:
        job_id = uuid4().hex
        directory = self.directory(job_id)
        directory.mkdir(parents=True)
        record = {"job_id": job_id, "plan_id": job_id, "status": "planned", "created_at": now(), "plan": plan}
        with self.transaction() as db:
            db.execute("INSERT INTO jobs VALUES (?, ?)", (job_id, json.dumps(record)))
        atomic_json(directory / "plan.json", plan)
        atomic_json(directory / "job.json", record)
        return record

    def get(self, job_id: str) -> dict:
        self.directory(job_id)
        with self.transaction() as db:
            row = db.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("No such job in this session.")
        return json.loads(row[0])

    def update(self, job_id: str, *, expected: set[str] | None = None, **values) -> dict:
        directory = self.directory(job_id)
        with self.transaction() as db:
            row = db.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise ValueError("No such job in this session.")
            record = json.loads(row[0])
            if expected is not None and record["status"] not in expected:
                return record
            record.update(values, updated_at=now())
            db.execute("UPDATE jobs SET data = ? WHERE id = ?", (json.dumps(record), job_id))
            # Serialize snapshots with state transitions. SQLite remains authoritative.
            atomic_json(directory / "job.json", record)
        return record

    def list(self) -> list[dict]:
        with self.transaction() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM jobs ORDER BY rowid DESC")]
