"""Bounded Python execution for generated workspace computations.

The runner deliberately accepts Python source rather than a shell command.  It
uses a private per-execution directory, a fresh interpreter, a scrubbed
environment, process-group cleanup, and POSIX resource limits.  The local
backend is intended for trusted deployments; production deployments should
place the same contract behind a container or microVM boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
from typing import Any
from uuid import uuid4

try:
    import resource
except ImportError:  # pragma: no cover - Windows does not expose POSIX rlimits.
    resource = None

from tools.infrastructure.tool_support.artifacts import artifact, input_path
from tools.infrastructure.tool_support.context import OperationContext
from tools.infrastructure.workspace import session_root, workspace_output_path


MAX_CODE_BYTES = 256 * 1024
MAX_INPUT_FILES = 16
MAX_INPUT_FILE_BYTES = 32 * 1024 * 1024
MAX_INPUT_TOTAL_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_FILES = 64
MAX_OUTPUT_FILE_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_TOTAL_BYTES = 128 * 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024
MAX_TIMEOUT_SECONDS = 120


def _relative_path(value: str, *, label: str) -> Path:
    candidate = Path(str(value or ""))
    if (
        not str(value).strip()
        or candidate.is_absolute()
        or candidate == Path(".")
        or "\\" in str(value)
        or ".." in candidate.parts
        or any(part.startswith(".") for part in candidate.parts)
    ):
        raise ValueError(f"{label} must be a visible relative path without parent traversal.")
    return candidate


def _resource_limits(timeout_seconds: int):
    """Return a POSIX pre-exec hook; unsupported limits are ignored."""

    if os.name != "posix" or resource is None:
        return None

    def limit_process() -> None:
        limits = (
            (resource.RLIMIT_CPU, (max(1, timeout_seconds + 1), max(1, timeout_seconds + 2))),
            (resource.RLIMIT_FSIZE, (MAX_OUTPUT_FILE_BYTES, MAX_OUTPUT_FILE_BYTES)),
            (resource.RLIMIT_NOFILE, (128, 128)),
        )
        for kind, value in limits:
            try:
                resource.setrlimit(kind, value)
            except (OSError, ValueError):
                pass

    return limit_process


def _safe_environment(run_dir: Path, input_map: dict[str, str]) -> dict[str, str]:
    """Keep only ordinary runtime variables and never pass application secrets."""

    allowed = {"PATH", "LANG", "LC_ALL", "TZ"}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment.update(
        {
            "HOME": str(run_dir),
            "TMPDIR": str(run_dir / "tmp"),
            "PYTHONNOUSERSITE": "1",
            "MPLBACKEND": "Agg",
            # These values are relative to the interpreter's working directory.
            "BIOAGENT_INPUT_DIR": "inputs",
            "BIOAGENT_OUTPUT_DIR": ".",
            "BIOAGENT_INPUTS_JSON": json.dumps(input_map, sort_keys=True),
        }
    )
    return environment


async def _capture(stream: asyncio.StreamReader | None) -> tuple[str, bool]:
    if stream is None:
        return "", False
    chunks: list[bytes] = []
    captured = 0
    truncated = False
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        remaining = MAX_CAPTURE_BYTES - captured
        if remaining > 0:
            keep = chunk[:remaining]
            chunks.append(keep)
            captured += len(keep)
        if len(chunk) > max(remaining, 0):
            truncated = True
    return b"".join(chunks).decode("utf-8", errors="replace"), truncated


def _copy_outputs(
    context: OperationContext,
    execution_id: str,
    run_dir: Path,
    requested: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Copy validated files from the private run directory into public outputs."""

    if requested:
        candidates = [_relative_path(path, label="output path") for path in requested]
    else:
        candidates = []
        for source in sorted(run_dir.rglob("*")):
            if not source.is_file() or source.name == "script.py" or "inputs" in source.relative_to(run_dir).parts:
                continue
            if any(part.startswith(".") for part in source.relative_to(run_dir).parts):
                continue
            candidates.append(source.relative_to(run_dir))
    if len(candidates) > MAX_OUTPUT_FILES:
        raise ValueError(f"Execution produced more than {MAX_OUTPUT_FILES} output files.")

    sources = [Path("script.py"), *candidates]
    total = 0
    files: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for relative in sources:
        key = relative.as_posix()
        if key in seen:
            continue
        seen.add(key)
        source = (run_dir / relative).resolve()
        if not source.is_file() or not source.is_relative_to(run_dir.resolve()):
            if relative == Path("script.py"):
                raise ValueError("The generated script is unavailable after execution.")
            if requested:
                missing.append(relative.as_posix())
            continue
        size = source.stat().st_size
        if size > MAX_OUTPUT_FILE_BYTES:
            raise ValueError(f"Output exceeds the {MAX_OUTPUT_FILE_BYTES} byte limit: {relative.as_posix()}")
        total += size
        if total > MAX_OUTPUT_TOTAL_BYTES:
            raise ValueError(f"Outputs exceed the {MAX_OUTPUT_TOTAL_BYTES} byte limit.")
        destination = workspace_output_path(context, "python_exec", execution_id, relative.as_posix())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        files.append(artifact(context, destination))
    return files, missing


async def execute_python(
    context: OperationContext,
    *,
    code: str,
    input_paths: list[str] | None = None,
    output_paths: list[str] | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Run generated Python and return a bounded result plus artifact metadata."""

    encoded = str(code).encode("utf-8")
    if not encoded.strip():
        raise ValueError("code must not be empty.")
    if len(encoded) > MAX_CODE_BYTES:
        raise ValueError(f"code exceeds the {MAX_CODE_BYTES} byte limit.")
    if not 1 <= int(timeout_seconds) <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}.")

    input_paths = list(input_paths or [])
    output_paths = list(output_paths or [])
    if len(input_paths) > MAX_INPUT_FILES:
        raise ValueError(f"At most {MAX_INPUT_FILES} input files are supported.")
    if len(set(input_paths)) != len(input_paths):
        raise ValueError("input_paths must not contain duplicates.")
    if len(output_paths) > MAX_OUTPUT_FILES:
        raise ValueError(f"At most {MAX_OUTPUT_FILES} output paths are supported.")
    requested_outputs = [_relative_path(path, label="output path") for path in output_paths]
    if any(path.parts[0] in {"inputs", "tmp"} for path in requested_outputs):
        raise ValueError("output_paths cannot target the execution input or temporary directories.")
    if len({path.as_posix() for path in requested_outputs}) != len(requested_outputs):
        raise ValueError("output_paths must not contain duplicates.")

    execution_id = uuid4().hex
    root = session_root(context)
    run_dir = root / ".python_exec" / execution_id
    inputs_dir = run_dir / "inputs"
    (run_dir / "tmp").mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    script = run_dir / "script.py"
    script.write_bytes(encoded)
    input_map: dict[str, str] = {}
    input_total = 0

    try:
        for index, public_path in enumerate(input_paths):
            _relative_path(public_path, label="input path")
            source = input_path(context, public_path, max_bytes=MAX_INPUT_FILE_BYTES)
            input_total += source.stat().st_size
            if input_total > MAX_INPUT_TOTAL_BYTES:
                raise ValueError(f"Input files exceed the {MAX_INPUT_TOTAL_BYTES} byte limit.")
            name = Path(public_path).name
            staged_name = f"{index:02d}_{name}"
            target = inputs_dir / staged_name
            shutil.copy2(source, target)
            input_map[str(public_path)] = (Path("inputs") / staged_name).as_posix()

        environment = _safe_environment(run_dir, input_map)
        command = [sys.executable, "-I", str(script)]
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=run_dir,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            preexec_fn=_resource_limits(int(timeout_seconds)),
        )
        stdout_task = asyncio.create_task(_capture(process.stdout))
        stderr_task = asyncio.create_task(_capture(process.stderr))
        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=int(timeout_seconds))
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, AttributeError):
                process.kill()
            await process.wait()
        stdout, stdout_truncated = await stdout_task
        stderr, stderr_truncated = await stderr_task
        duration_ms = int((time.monotonic() - started) * 1000)
        files, missing_outputs = _copy_outputs(
            context,
            execution_id,
            run_dir,
            [path.as_posix() for path in requested_outputs],
        )
        summary = (
            f"Python execution timed out after {timeout_seconds}s."
            if timed_out
            else f"Python execution exited with code {process.returncode}."
        )
        if missing_outputs:
            summary += f" Missing expected outputs: {', '.join(missing_outputs)}."
        return {
            "execution_id": execution_id,
            "script_path": next(item["path"] for item in files if item["name"] == "script.py"),
            "returncode": None if timed_out else process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "output_paths": [item["path"] for item in files if item["name"] != "script.py"],
            "missing_outputs": missing_outputs,
            "code_sha256": hashlib.sha256(encoded).hexdigest(),
            "summary": summary,
        }, files
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


__all__ = ["execute_python", "MAX_CODE_BYTES", "MAX_TIMEOUT_SECONDS"]
