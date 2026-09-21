"""Engine process adapter: live disk logs inside a supervised local worker."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

CompletedProcess = subprocess.CompletedProcess
TimeoutExpired = subprocess.TimeoutExpired


def tail(path: Path, limit: int = 16000) -> str:
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - limit))
        return handle.read(limit).decode("utf-8", errors="replace")


def run(command, **kwargs):
    job = os.environ.get("AGENT_LOCAL_JOB_DIR")
    if not job:
        return subprocess.run(command, **kwargs)
    directory = Path(job)
    stdout_path, stderr_path = directory / "stdout.log", directory / "stderr.log"
    kwargs.pop("capture_output", None)
    kwargs.pop("text", None)
    kwargs.pop("check", None)
    # Engine scratch files must also stay in the job's execution directory.
    kwargs["cwd"] = directory / "outputs"
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, check=False, **kwargs)
    return CompletedProcess(command, completed.returncode, tail(stdout_path), tail(stderr_path))
