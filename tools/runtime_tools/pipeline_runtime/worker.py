"""Detached local worker, supervised independently of the agent's event loop."""
from __future__ import annotations

import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import traceback

from .service import execute_engine
from .store import JobStore, atomic_json, now


def work(root: Path, job_id: str) -> int:
    store = JobStore(root)
    record = store.get(job_id)
    if record["status"] != "queued":
        return 1
    record = store.update(job_id, expected={"queued"}, status="running", started_at=now())
    if record["status"] != "running":
        return 1
    directory = store.directory(job_id)
    os.environ["BIOAGENT_LOCAL_JOB_DIR"] = str(directory)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = str(record["plan"]["cores"])
    # Linux address-space limit is inherited by engine processes. It is per process,
    # not a container/cgroup aggregate memory or CPU quota.
    memory = record["plan"]["max_memory_mb"] * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))

    def expire():
        store.update(job_id, expected={"running"}, status="timed_out", finished_at=now(), error="Pipeline exceeded its timeout.")
        os.killpg(os.getpid(), signal.SIGKILL)

    timer = threading.Timer(record["plan"]["timeout_seconds"], expire)
    timer.daemon = True
    timer.start()
    try:
        result = execute_engine(root, record)
        atomic_json(directory / "output-manifest.json", result["output_records"])
        store.update(job_id, expected={"running"}, status="succeeded", finished_at=now(), exit_code=0, result=result)
        return 0
    except subprocess.TimeoutExpired as exc:
        traceback.print_exc()
        store.update(job_id, expected={"running"}, status="timed_out", finished_at=now(), exit_code=124, error=str(exc))
        return 124
    except Exception as exc:
        traceback.print_exc()
        store.update(job_id, expected={"running"}, status="failed", finished_at=now(), exit_code=1, error=str(exc))
        return 1
    finally:
        timer.cancel()
        # A timed-out/failed engine may have left descendants. Worker is the group
        # leader; terminating the group also prevents accidental background work.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.killpg(os.getpid(), signal.SIGTERM)


if __name__ == "__main__":
    raise SystemExit(work(Path(sys.argv[1]).resolve(), sys.argv[2]))
