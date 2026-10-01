"""Wait for pipelines launched by this request without spending model turns."""
from __future__ import annotations

import asyncio
from pathlib import Path

from tools.infrastructure.pipeline_engine.commands import parse_command
from tools.infrastructure.pipeline_engine import service
from tools.infrastructure.pipeline_engine.store import TERMINAL


async def collect_started_pipelines(context, emit=None, *, poll_interval=2.0):
    started, collected = set(), set()
    for item in context.tool_results:
        if item.get("tool") != "pipeline_shell":
            continue
        try:
            args = parse_command(item.get("arguments", {}).get("command", ""))
        except ValueError:
            continue
        value = item.get("result", {})
        if args.operation == "run" and value.get("status") in {"queued", "running", "succeeded"}:
            started.add(args.plan_id)
        elif args.operation == "results" and value.get("status") == "succeeded":
            collected.add(args.job_id)
    collected.update(event.get("data", {}).get("job_id") for event in context.events
                     if event.get("event") == "pipeline_completion_collected")
    pending = started - collected
    if not pending:
        return []
    root = Path(context.run["session_dir"])
    previous, completed = {}, []
    while pending:
        for job_id in sorted(pending):
            value = await asyncio.to_thread(service.status, root, job_id)
            status = value["status"]
            if previous.get(job_id) != status:
                progress = {"job_id": job_id, "pipeline_name": value["pipeline_name"], "status": status}
                context.record("pipeline_job_status", **progress)
                if emit:
                    emit("pipeline_job_status", context.public(progress))
                previous[job_id] = status
            if status not in TERMINAL:
                continue
            if status == "succeeded":
                try:
                    value = await asyncio.to_thread(service.results, root, job_id)
                except (ValueError, OSError) as exc:
                    value = {**value, "status": "error", "error": f"Output verification failed: {exc}", "files": []}
            # Preserve the actual read-only result in the same evidence contract
            # as model-issued pipeline_shell commands. Never submit another run.
            value = context.public(value)
            command = f"agent-pipeline results --job-id {job_id}"
            context.tool_results.append({"tool": "pipeline_shell", "arguments": {"command": command}, "result": value})
            context.record("pipeline_completion_collected", job_id=job_id, status=value["status"])
            completed.append(value)
            pending.remove(job_id)
        if pending:
            await asyncio.sleep(poll_interval)
    return completed
