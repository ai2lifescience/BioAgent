"""SQLite-backed agent jobs with bounded, detached local workers."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Lock, Thread
from uuid import uuid4

from tools.infrastructure.workspace.public import public_payload


TERMINAL = {"succeeded", "failed", "blocked", "pending_approval", "interrupted"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result_status(result: dict) -> str:
    status = result.get("status")
    if status == "pending_approval":
        return "pending_approval"
    if status == "error":
        return "failed"
    if status == "blocked":
        return "blocked"
    return "succeeded"


class RunQueue:
    def __init__(self, path: str | Path | None = None, *, max_workers: int | None = None) -> None:
        self.path = Path(path or os.getenv("AGENT_RUN_DB", "runtime/agent_runs.sqlite3")).resolve()
        self.max_workers = max(1, int(max_workers if max_workers is not None else os.getenv("AGENT_RUN_WORKERS", "2")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def db(self, *, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=30)
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

    def _init(self) -> None:
        with self.db(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request TEXT NOT NULL,
                model_key TEXT NOT NULL, max_turns INTEGER NOT NULL, status TEXT NOT NULL,
                result TEXT, error TEXT, pid INTEGER, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, approval TEXT
            )""")
            if "approval" not in {row["name"] for row in db.execute("PRAGMA table_info(runs)")}:
                db.execute("ALTER TABLE runs ADD COLUMN approval TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS run_events (
                run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS runs_by_session ON runs(session_id, created_at)")

    @staticmethod
    def _event(db, run_id: str, event: str, payload: dict) -> None:
        # Caller holds the SQLite write lock: parallel tools cannot allocate
        # the same sequence number, even from different worker processes.
        row = db.execute("SELECT COALESCE(MAX(sequence), -1) + 1 AS next FROM run_events WHERE run_id=?", (run_id,)).fetchone()
        db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?)",
                   (run_id, row["next"], event, json.dumps(payload, ensure_ascii=False), now()))

    def enqueue(self, request: str, session_id: str | None, model_key: str, max_turns: int) -> dict:
        if not str(request).strip():
            raise ValueError("request is required")
        run_id, identifier, timestamp = uuid4().hex, session_id or str(uuid4()), now()
        with self.db(write=True) as db:
            active = db.execute(
                "SELECT run_id FROM runs WHERE session_id=? AND status IN ('queued','running','pending_approval') LIMIT 1",
                (identifier,),
            ).fetchone()
            if active:
                raise ValueError("This session already has an active run.")
            db.execute("""INSERT INTO runs
                (run_id,session_id,request,model_key,max_turns,status,created_at,updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)""",
                (run_id, identifier, request, model_key, max(1, int(max_turns)), timestamp, timestamp))
            self._event(db, run_id, "queued", {"message": "Agent run queued.", "run_id": run_id, "session_id": identifier})
        self.dispatch()
        return self.get(run_id)

    def resume(self, session_id: str, approved: bool, approval_id: str) -> dict | None:
        """Atomically queue one decision on a paused job; reject duplicate/stale decisions."""
        if type(approved) is not bool or not approval_id:
            raise ValueError("An approval_id and explicit boolean decision are required.")
        with self.db(write=True) as db:
            row = db.execute("SELECT * FROM runs WHERE session_id=? AND status='pending_approval'", (session_id,)).fetchone()
            if row is None:
                return None
            result = json.loads(row["result"] or "{}")
            if approval_id not in {item["approval_id"] for item in result.get("approvals", [])}:
                raise ValueError("Unknown or expired approval_id for this session.")
            run_id = row["run_id"]
            decision = json.dumps({"approved": approved, "approval_id": approval_id})
            db.execute("UPDATE runs SET status='queued', approval=?, result=NULL, error=NULL, pid=NULL, updated_at=? WHERE run_id=?",
                       (decision, now(), run_id))
            self._event(db, run_id, "queued", {"message": "Approval received. Resume queued.", "run_id": run_id})
        self.dispatch()
        return self.get(run_id)

    def dispatch(self) -> None:
        """Launch FIFO work up to the worker limit, with an atomic claim and PID."""
        while True:
            with self.db(write=True) as db:
                active = db.execute("SELECT COUNT(*) FROM runs WHERE status='running'").fetchone()[0]
                if active >= self.max_workers:
                    return
                row = db.execute("SELECT run_id FROM runs WHERE status='queued' ORDER BY updated_at, run_id LIMIT 1").fetchone()
                if row is None:
                    return
                run_id = row["run_id"]
                try:
                    # Keep the claim transaction open until the PID is saved.
                    # A worker waits for this transaction before reading its job.
                    process = subprocess.Popen(
                        [sys.executable, "-m", "harness.jobs", "worker", str(self.path), run_id],
                        cwd=Path(__file__).resolve().parents[1],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**os.environ, "PYTHONUNBUFFERED": "1", "AGENT_RUN_WORKERS": str(self.max_workers)},
                        start_new_session=True,
                    )
                except Exception as exc:
                    error = f"Could not start run worker: {exc}"
                    db.execute("UPDATE runs SET status='failed', error=?, updated_at=? WHERE run_id=?", (error, now(), run_id))
                    self._event(db, run_id, "failed", {"error": error})
                else:
                    db.execute("UPDATE runs SET status='running', pid=?, updated_at=? WHERE run_id=?", (process.pid, now(), run_id))
                    Thread(target=process.wait, daemon=True).start()

    def recover(self) -> None:
        """Keep surviving workers; mark dead ones interrupted without replaying side effects."""
        with self.db(write=True) as db:
            rows = db.execute("SELECT run_id,pid FROM runs WHERE status='running'").fetchall()
            for row in rows:
                if not row["pid"] or not _pid_alive(int(row["pid"])):
                    error = "Run worker exited before completion. Review partial work before retrying."
                    db.execute("UPDATE runs SET status='interrupted', error=?, updated_at=? WHERE run_id=?", (error, now(), row["run_id"]))
                    self._event(db, row["run_id"], "interrupted", {"status": "interrupted", "error": error})
        self.dispatch()

    def get(self, run_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("No such agent run.")
        result = dict(row)
        for key in ("result", "approval"):
            if result.get(key):
                result[key] = json.loads(result[key])
        return result

    def pending_for_session(self, session_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT run_id FROM runs WHERE session_id=? AND status='pending_approval' ORDER BY updated_at DESC LIMIT 1", (session_id,)).fetchone()
        return self.get(row["run_id"]) if row else None

    def list(self, session_id: str | None = None) -> list[dict]:
        with self.db() as db:
            if session_id:
                rows = db.execute("SELECT run_id FROM runs WHERE session_id=? ORDER BY created_at DESC LIMIT 100", (session_id,)).fetchall()
            else:
                rows = db.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 100").fetchall()
        return [self.get(row["run_id"]) for row in rows]

    def update(self, run_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> dict:
        with self.db(write=True) as db:
            db.execute("UPDATE runs SET status=?, result=?, error=?, updated_at=? WHERE run_id=?",
                       (status, json.dumps(result) if result is not None else None, error, now(), run_id))
            self._event(db, run_id, status, {"status": status, **({"error": error} if error else {})})
        return self.get(run_id)

    def event(self, run_id: str, event: str, payload: dict) -> None:
        with self.db(write=True) as db:
            self._event(db, run_id, event, payload)

    def events(self, run_id: str, after: int = -1) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT sequence,event,payload,created_at FROM run_events WHERE run_id=? AND sequence>? ORDER BY sequence", (run_id, after)).fetchall()
        return [{"sequence": r["sequence"], "event": r["event"], "payload": json.loads(r["payload"]), "created_at": r["created_at"]} for r in rows]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        # A zombie has already exited, though kill(pid, 0) still succeeds.
        return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


_queue: RunQueue | None = None
_queue_lock = Lock()


def get_queue() -> RunQueue:
    """Initialize the default queue on first use, safely across HTTP threads."""
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = RunQueue()
        return _queue


def execute_job(queue: RunQueue, run_id: str) -> int:
    """Execute one durable agent run in the worker process."""
    job = queue.get(run_id)
    if job["status"] not in {"queued", "running"}:
        return 0
    queue.event(run_id, "started", {"message": "Agent run started.", "run_id": run_id})

    def log(message: str) -> None:
        queue.event(run_id, "log", {"message": str(message)})

    pending_deltas: list[str] = []
    pending_delta_size = 0

    def flush_deltas() -> None:
        nonlocal pending_delta_size
        if pending_deltas:
            queue.event(run_id, "sdk_raw_response", {
                "sdk_type": "raw_response_event",
                "data_type": "response.output_text.delta",
                "delta": public_payload("".join(pending_deltas)),
            })
            pending_deltas.clear()
            pending_delta_size = 0

    def sdk_event(name: str, payload: dict) -> None:
        nonlocal pending_delta_size
        if name == "sdk_raw_response" and payload.get("data_type") == "response.output_text.delta":
            delta = str(payload.get("delta") or "")
            if delta:
                pending_deltas.append(delta)
                pending_delta_size += len(delta)
                if pending_delta_size >= 256:
                    flush_deltas()
            return
        flush_deltas()
        queue.event(run_id, name, payload)

    try:
        from .runtime import resume_agent, run_agent
        if job.get("approval"):
            result = resume_agent(job["session_id"], **job["approval"], log_fn=log, event_fn=sdk_event)
        else:
            result = run_agent(
                job["request"], session_id=job["session_id"],
                model_key=job["model_key"], max_turns=job["max_turns"],
                log_fn=log, event_fn=sdk_event,
            )
        flush_deltas()
        queue_status = result_status(result)
        queue.update(
            run_id,
            queue_status,
            result=result,
            error=result.get("answer") if queue_status == "failed" else None,
        )
        return 0
    except Exception as exc:
        flush_deltas()
        queue.update(run_id, "failed", error=str(exc))
        return 1
    finally:
        queue.dispatch()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("worker", help="Execute one queued agent run")
    worker.add_argument("database", help="Path to the agent jobs database")
    worker.add_argument("run_id", help="Identifier of the queued run")
    args = parser.parse_args(argv)
    return execute_job(RunQueue(args.database), args.run_id)


if __name__ == "__main__":
    raise SystemExit(main())
