"""Pipeline discovery, validated plans, local jobs, and bounded result collection."""
from __future__ import annotations

import copy
import csv
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile

from .store import JobStore, TERMINAL, atomic_json, confined, now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINES_ROOT = PROJECT_ROOT / "tools" / "runtime_tools" / "pipelines"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def definition(name: str):
    from tools.runtime_tools.pipeline_runtime.engine.config import load_runner_config, load_pipeline_config
    from tools.runtime_tools.pipeline_runtime.engine.paths import resolve_pipeline_dir, resolve_pipeline_name
    directory = resolve_pipeline_dir(resolve_pipeline_name(name))
    manifest, _ = load_runner_config(directory)
    config, _ = load_pipeline_config(directory, manifest)
    return directory, manifest, config


def definition_hash(directory: Path) -> str:
    # Include imported workflow code/configs, excluding generated files and sample data.
    values = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if any(part.startswith(".") or part in {"data", "__pycache__"} for part in relative.parts):
            continue
        if path.is_file():
            if not path.resolve().is_relative_to(directory):
                raise ValueError("Pipeline definitions cannot link outside their directory.")
            values.append((relative.as_posix(), digest(path)))
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def catalog() -> list[dict]:
    from tools.runtime_tools.pipeline_runtime.engine.inputs import pipeline_input_specs
    from tools.runtime_tools.pipeline_runtime.engine.outputs import pipeline_output_specs
    entries = []
    for path in sorted(PIPELINES_ROOT.iterdir()):
        if not (path / "runner.yaml").is_file():
            continue
        try:
            _, manifest, config = definition(path.name)
            entries.append({
                "name": path.name,
                "display_name": manifest.get("display_name") or path.name,
                "visibility": manifest.get("visibility", "public"),
                "description": manifest.get("description", ""),
                "use_when": manifest.get("use_when", []),
                "avoid_when": manifest.get("avoid_when", []),
                "input_summary": manifest.get("input_summary", ""),
                "output_summary": manifest.get("output_summary", ""),
                "limitations": manifest.get("limitations", ""),
                "examples": manifest.get("examples", []),
                "execution": manifest.get("execution", {}),
                "engine": manifest.get("engine"),
                "inputs": pipeline_input_specs(manifest),
                "outputs": pipeline_output_specs(manifest),
                "parameters": manifest.get("param_overrides") or config.get("params", {}),
                "timeout_seconds": manifest.get("timeout", 300),
            })
        except (ValueError, OSError) as exc:
            entries.append({"name": path.name, "error": str(exc)})
    return entries


def files(root: Path) -> list[dict]:
    found = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(p.startswith(".") for p in relative.parts) or path.is_symlink() or not path.is_file():
            continue
        if path.resolve().is_relative_to(root.resolve()):
            found.append({"workspace_path": relative.as_posix(), "name": path.name, "size": path.stat().st_size})
    return sorted(found, key=lambda item: item["workspace_path"])


def stage_example(root: Path, name: str) -> dict:
    directory, _, _ = definition(name)
    source = directory / "data" / "input"
    from uuid import uuid4
    destination = confined(root, f"uploads/examples/{name}-{uuid4().hex[:8]}")
    destination.mkdir(parents=True)
    staged = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        staged.append({"workspace_path": target.relative_to(root).as_posix(), "size": target.stat().st_size})
    return {"pipeline_name": name, "files": staged, "example_data": True}


def plan(root: Path, name: str, inputs: dict, params: dict, cores: int = 1,
         timeout: int | None = None, dry_run: bool = False) -> dict:
    from tools.runtime_tools.pipeline_runtime.engine.inputs import pipeline_input_specs, validate_input_value
    from tools.runtime_tools.pipeline_runtime.engine.outputs import pipeline_output_specs
    from tools.runtime_tools.pipeline_runtime.engine.config import apply_config_overrides, apply_runner_param_overrides, apply_runner_preset
    directory, manifest, config = definition(name)
    engine = manifest.get("engine")
    if engine not in {"shell", "snakemake", "nextflow", "wdl"}:
        raise ValueError("Unsupported local engine.")
    if engine == "wdl" and manifest.get("wdl_engine", "miniwdl") != "miniwdl":
        raise ValueError("Local WDL execution requires miniwdl; remote Cromwell jobs use the legacy backend.")
    if dry_run and engine == "shell":
        raise ValueError("Shell pipelines do not declare a dry-run command; use plan to validate inputs.")
    max_timeout = min(86400, int(manifest.get("timeout", 300)))
    timeout = max_timeout if timeout is None else timeout
    max_cores = min(64, int(manifest.get("resources", {}).get("max_cores", 4)))
    if not 1 <= timeout <= max_timeout or not 1 <= cores <= max_cores:
        raise ValueError(f"Timeout must be 1..{max_timeout} seconds and cores 1..{max_cores}.")
    specs = pipeline_input_specs(manifest)
    if set(inputs) - set(specs):
        raise ValueError(f"Unknown input slots: {sorted(set(inputs) - set(specs))}")
    missing = [slot for slot, spec in specs.items() if spec["required"] and not inputs.get(slot)]
    if missing:
        return {"status": "needs_input", "needs_input": True, "pipeline_name": name,
                "requested_inputs": [{**specs[slot], "slot": slot} for slot in missing]}
    records = {}
    for slot, value in inputs.items():
        spec = specs[slot]
        values = value if isinstance(value, list) else [value]
        if not values or (not spec["multiple"] and len(values) != 1):
            raise ValueError(f"Input {slot} has invalid file cardinality.")
        paths = [confined(root, str(item)) for item in values]
        if any(not path.is_file() for path in paths):
            raise ValueError(f"Input {slot} must contain existing regular files.")
        validate_input_value(paths if spec["multiple"] else paths[0], spec)
        records[slot] = [{"path": p.relative_to(root).as_posix(), "sha256": digest(p), "size": p.stat().st_size} for p in paths]
    updated = copy.deepcopy(config)
    for key, spec in (manifest.get("param_overrides") or {}).items():
        if isinstance(spec, dict) and spec.get("required") and params.get(key) in (None, ""):
            return {"status": "needs_parameters", "required_parameters": [{"name": key, **spec}]}
    selected = apply_runner_preset(updated, params, manifest)
    if apply_runner_param_overrides(updated, selected, manifest) is None:
        apply_config_overrides(updated, selected)
    outputs = pipeline_output_specs(manifest)
    if not outputs:
        raise ValueError("Local pipelines must declare their outputs in runner.yaml.")
    # Reject output escapes before presenting the plan, including parameter overrides.
    for spec in outputs.values():
        value = updated.get(spec["config_key"]) or spec["default"]
        confined(root, str(value))
    memory_mb = int(manifest.get("resources", {}).get("max_memory_mb", 8192))
    if not 128 <= memory_mb <= 65536:
        raise ValueError("Pipeline max_memory_mb must be between 128 and 65536.")
    record = JobStore(root).create({"pipeline_name": name, "engine": engine,
        "inputs": records, "parameters": selected, "cores": cores, "timeout_seconds": timeout,
        "max_memory_mb": memory_mb, "dry_run": dry_run,
        "definition_sha256": definition_hash(directory), "outputs": outputs})
    return {**summary(record), "plan": record["plan"],
            "command": f"agent-pipeline run --plan-id {record['plan_id']}"}


def verify(root: Path, plan: dict) -> None:
    directory, _, _ = definition(plan["pipeline_name"])
    if definition_hash(directory) != plan["definition_sha256"]:
        raise ValueError("Pipeline definition changed since planning; create a new plan.")
    for values in plan["inputs"].values():
        for item in values:
            path = confined(root, item["path"])
            if not path.is_file() or digest(path) != item["sha256"]:
                raise ValueError("Input changed since planning; create a new plan.")


def identity(pid: int) -> str | None:
    """Linux process birth identity; do not signal a reused PID or a zombie."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return fields[19]
    except (OSError, IndexError):
        return None


def alive(record: dict) -> bool:
    return bool(record.get("pid") and record.get("process_identity") and
                identity(record["pid"]) == record["process_identity"])


def summary(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in {"plan", "result", "process_identity", "pid"}}


def start(root: Path, plan_id: str) -> dict:
    store = JobStore(root)
    record = store.get(plan_id)
    if record["status"] != "planned":
        return status(root, plan_id)
    verify(root, record["plan"])
    # Serialize launch with the transition to queued so duplicate calls cannot spawn workers.
    directory = store.directory(plan_id)
    with store.transaction() as db:
        row = json.loads(db.execute("SELECT data FROM jobs WHERE id = ?", (plan_id,)).fetchone()[0])
        if row["status"] != "planned":
            return summary(row)
        # Only carry runtime paths and locale, never provider API keys into scripts.
        env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "JAVA_HOME", "CONDA_PREFIX") if key in os.environ}
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", os.defpath)
        env.update(PYTHONPATH=str(PROJECT_ROOT), PYTHONUNBUFFERED="1")
        with (directory / "stdout.log").open("ab") as stdout, (directory / "stderr.log").open("ab") as stderr:
            process = subprocess.Popen([sys.executable, "-m", "tools.runtime_tools.pipeline_runtime.worker", str(root), plan_id],
                cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                env=env, start_new_session=True)
        row.update(status="queued", pid=process.pid, process_identity=identity(process.pid), queued_at=now())
        db.execute("UPDATE jobs SET data = ? WHERE id = ?", (json.dumps(row), plan_id))
        atomic_json(directory / "job.json", row)
    # Reap our child after completion without tying worker life to the request's event loop.
    threading.Thread(target=process.wait, daemon=True).start()
    return summary(row)


def status(root: Path, job_id: str) -> dict:
    store = JobStore(root)
    record = store.get(job_id)
    if record["status"] in {"queued", "running"} and not alive(record):
        record = store.update(job_id, expected={"queued", "running"}, status="interrupted",
                              error="Worker exited without completion; create a new plan to rerun.", finished_at=now())
    return {**summary(record), "pipeline_name": record["plan"]["pipeline_name"],
            "logs": {name: f"runs/{job_id}/{name}.log" for name in ("stdout", "stderr")}}


def wait(root: Path, job_id: str, seconds: float) -> dict:
    if not math.isfinite(seconds) or not 0 <= seconds <= 30:
        raise ValueError("Wait must be between 0 and 30 seconds.")
    deadline = time.monotonic() + seconds
    while True:
        record = status(root, job_id)
        if record["status"] in TERMINAL or record["status"] == "planned" or time.monotonic() >= deadline:
            return record
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))


def cancel(root: Path, job_id: str) -> dict:
    store = JobStore(root)
    record = store.get(job_id)
    if record["status"] in TERMINAL:
        return status(root, job_id)
    # Mark before signalling so neither worker success nor stale status can overwrite it.
    updated = store.update(job_id, expected={"planned", "queued", "running"}, status="cancelled", finished_at=now())
    if updated["status"] == "cancelled" and alive(updated):
        try:
            os.killpg(updated["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    return summary(updated)


def results(root: Path, job_id: str, max_rows: int = 10) -> dict:
    if not 1 <= max_rows <= 50:
        raise ValueError("Table preview limit must be between 1 and 50.")
    store = JobStore(root)
    record = store.get(job_id)
    if record["status"] != "succeeded":
        return {**status(root, job_id), "files": [], "message": "Results require a succeeded job."}
    outputs = record.get("result", {}).get("output_records", [])
    directory = store.directory(job_id)
    selected, tables, metrics = [], [], {}
    for item in outputs:
        if not item.get("exists"):
            continue
        path = confined(root, item["workspace_path"])
        if not path.is_relative_to(directory) or not path.is_file() or digest(path) != item["sha256"]:
            raise ValueError("An output is missing, modified, or outside its job directory.")
        selected.append((item, path))
        if item.get("kind") == "metrics" and path.stat().st_size <= 1_000_000:
            metrics = json.loads(path.read_text())
        if path.suffix in {".tsv", ".csv"}:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t" if path.suffix == ".tsv" else ",")
                rows = []
                for _, row in zip(range(max_rows + 1), reader):
                    rows.append(row)
                tables.append({"name": path.name, "columns": reader.fieldnames, "rows": rows[:max_rows], "truncated": len(rows) > max_rows})
    archive_path = confined(root, f"runs/{job_id}/results.zip")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for _, path in selected:
            archive.write(path, path.relative_to(directory).as_posix())
        for name in ("stdout.log", "stderr.log", "plan.json", "output-manifest.json"):
            path = confined(root, f"runs/{job_id}/{name}")
            if path.is_file():
                archive.write(path, name)
    return {"status": "succeeded", "job_id": job_id, "pipeline_name": record["plan"]["pipeline_name"],
            "files": [item for item, _ in selected], "metrics": metrics, "tables": tables,
            "bundle_path": archive_path.relative_to(root).as_posix()}


def execute_engine(root: Path, record: dict) -> dict:
    """Reuse all four engine adapters with immutable input copies and job-local outputs."""
    from tools.runtime_tools.pipeline_runtime.engine.inputs import pipeline_input_specs
    from tools.runtime_tools.pipeline_runtime.engine.runner import prepare_pipeline_context
    plan = record["plan"]
    verify(root, plan)
    store = JobStore(root)
    directory = store.directory(record["job_id"])
    _, manifest, _ = definition(plan["pipeline_name"])
    specs = pipeline_input_specs(manifest)
    inputs = {}
    for slot, items in plan["inputs"].items():
        copies = []
        for index, item in enumerate(items):
            target = confined(root, f"runs/{record['job_id']}/inputs/{slot}/{index}_{Path(item['path']).name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(confined(root, item["path"]), target)
            if digest(target) != item["sha256"]:
                raise ValueError("Input changed while being staged.")
            copies.append(str(target))
        inputs[slot] = ";".join(copies) if specs[slot]["multiple"] else copies[0]
    atomic_json(directory / "inputs.json", inputs)
    context = prepare_pipeline_context(pipeline_name=plan["pipeline_name"], input_overrides=inputs,
        config_overrides=plan["parameters"], artifact_dir=str(directory), run_id="execution", timeout=plan["timeout_seconds"])
    output_dir = confined(root, f"runs/{record['job_id']}/outputs")
    output_dir.mkdir(exist_ok=True)
    context = replace(context, run_dir=output_dir, output_dir=output_dir)
    if plan["engine"] == "shell":
        from tools.runtime_tools.pipeline_runtime.engine.shell import run_shell_pipeline
        result = run_shell_pipeline(context)
    elif plan["engine"] == "snakemake":
        from tools.runtime_tools.pipeline_runtime.engine.snakemake import run_snakemake_pipeline
        result = run_snakemake_pipeline(context, cores=plan["cores"], dry_run=plan["dry_run"])
    elif plan["engine"] == "nextflow":
        from tools.runtime_tools.pipeline_runtime.engine.nextflow import run_nextflow_pipeline
        result = run_nextflow_pipeline(context, cores=plan["cores"], dry_run=plan["dry_run"])
    else:
        from tools.runtime_tools.pipeline_runtime.engine.wdl import run_wdl_pipeline
        result = run_wdl_pipeline(context, dry_run=plan["dry_run"])
    for item in result["output_records"]:
        path = Path(item["path"]).resolve()
        if not path.is_relative_to(output_dir):
            raise ValueError("Pipeline output escaped its job directory.")
        item["workspace_path"] = path.relative_to(root).as_posix()
        if item["exists"]:
            if not path.is_file():
                raise ValueError("Declared outputs must be regular files.")
            item.update(sha256=digest(path), size=path.stat().st_size)
    return result
