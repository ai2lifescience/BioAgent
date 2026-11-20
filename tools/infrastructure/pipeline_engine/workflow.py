"""Persist, schedule and reconcile approved pipeline graphs."""
from contextlib import closing, contextmanager
import fcntl
import json
import logging
from pathlib import Path
import re
import sqlite3
from threading import Event, Thread
from uuid import uuid4

from auth import AccessDenied, AuthError, Principal, current_principal, principal_scope
from . import contracts, dependency_graph, service
from .engine.inputs import pipeline_input_specs
from .store import TERMINAL, CapacityReached, now

ACTIVE = {"queued", "running", "cancelling"}
STEP_DONE = TERMINAL | {"blocked"}
MAX_PARALLEL = 2
ID = re.compile(r"[a-f0-9]{32}")
log = logging.getLogger(__name__)


class OutputUnavailable(ValueError):
    """An input cannot be resolved from a prerequisite's outputs."""


class WorkflowStore:
    def __init__(self, access):
        self.directory = access.metadata_root / ".pipeline-workflows"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.directory / "workflows.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                status TEXT NOT NULL, data TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS workflow_status ON workflows(status)")
            db.execute("CREATE INDEX IF NOT EXISTS workflow_session ON workflows(session_id)")

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.database, timeout=30)) as db, db:
            yield db

    @contextmanager
    def lock(self, identifier):
        if not ID.fullmatch(identifier):
            raise ValueError("Invalid workflow ID.")
        with (self.directory / f"{identifier}.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def save(self, workflow):
        with self.connect() as db:
            db.execute("""INSERT INTO workflows VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status, data=excluded.data""",
                (workflow["workflow_id"], workflow["session_id"], workflow["status"], json.dumps(workflow)))

    def get(self, session, identifier):
        if not ID.fullmatch(identifier):
            raise ValueError("Invalid workflow ID.")
        with self.connect() as db:
            row = db.execute("SELECT data FROM workflows WHERE id=? AND session_id=?", (identifier, session)).fetchone()
        if row is None:
            raise ValueError("Workflow not found.")
        return json.loads(row[0])

    def list(self, session):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM workflows WHERE session_id=? ORDER BY rowid DESC LIMIT 32", (session,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def active(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM workflows WHERE status IN ('queued','running','cancelling')").fetchall()
        return [json.loads(row[0]) for row in rows]


def _session(root, access):
    root = Path(root)
    if access.workspace(root.name).resolve() != root.resolve():
        raise ValueError("Workflow workspace does not match the owned session.")
    return root.resolve()


def _public(workflow):
    steps = []
    for step in workflow["steps"].values():
        fields = ("id", "pipeline", "depends_on", "inputs", "params", "cores", "timeout", "reason", "input_reasons",
                  "status", "job_id", "error", "files", "bundle_path")
        steps.append({key: step[key] for key in fields if key in step})
    return {**_summary(workflow), "steps": steps}


def _summary(workflow):
    return {"workflow_id": workflow["workflow_id"], "status": workflow["status"],
            "created_at": workflow["created_at"], "step_count": len(workflow["steps"])}


def _definition(pipeline, isolated):
    return (contracts.definition if isolated else service.definition)(pipeline)


def plan(root, steps, *, access, isolated):
    root = _session(root, access)
    graph, fingerprints = dependency_graph.build(root, steps, isolated=isolated)
    workflow = {"workflow_id": uuid4().hex, "session_id": root.name, "owner": current_principal().user_id,
                "status": "planned", "created_at": now(), "isolated": isolated,
                "steps": graph, "fingerprints": fingerprints, "imported": {}}
    WorkflowStore(access).save(workflow)
    return _public(workflow)


def status(root, identifier, *, access):
    root = _session(root, access)
    return _public(WorkflowStore(access).get(root.name, identifier))


def start(root, identifier, *, access, isolated):
    root = _session(root, access)
    store = WorkflowStore(access)
    with store.lock(identifier):
        workflow = store.get(root.name, identifier)
        _check_backend(workflow, isolated)
        if workflow["status"] == "planned":
            workflow["status"] = "queued"
            store.save(workflow)
        return _public(workflow)


def _check_backend(workflow, isolated):
    if workflow["isolated"] != isolated:
        raise ValueError("This workflow must run with the execution backend it was planned for.")


def _job(root, operation, identifier, *, access, isolated):
    if isolated:
        from . import broker
        flag = "plan-id" if operation == "run" else "job-id"
        return broker.dispatch(root, f"agent-pipeline {operation} --{flag} {identifier}", access=access)
    if operation == "results":
        return service.results(root, identifier, include_bundle=False)
    return getattr(service, "start" if operation == "run" else operation)(root, identifier)


def _artifacts(root, workflow, binding, access):
    upstream = workflow["steps"][binding["step"]]
    name = binding["output"]
    pattern = re.compile(re.escape(name) + r"(?:\[\d+\])?")
    files = [item for item in upstream.get("files", []) if pattern.fullmatch(item["output_name"])]
    if not files:
        raise OutputUnavailable(f"Required output {upstream['id']}.{name} is unavailable.")
    for item in files:
        if item["remote"]:
            from . import broker
            source = item["workspace_path"]
            if source not in workflow["imported"]:
                file = broker.materialize(root, source, access=access)
                workflow["imported"][source] = (file["workspace_path"], file["sha256"])
            yield workflow["imported"][source]
        else:
            yield item["workspace_path"], item["sha256"]


def _create_job(root, workflow, step, access, isolated):
    directory, manifest, _ = _definition(step["pipeline"], isolated)
    if service.definition_hash(directory) != step["definition_sha256"]:
        raise ValueError("Pipeline definition changed after planning. Create a new workflow plan.")
    inputs, digests = {}, {}
    specs = pipeline_input_specs(manifest)
    for slot, value in step["inputs"].items():
        resolved = []
        for binding in dependency_graph.input_bindings(value):
            if isinstance(binding, str):
                resolved.append((binding, workflow["fingerprints"][binding]["sha256"]))
            else:
                resolved.extend(_artifacts(root, workflow, binding, access))
        if not specs[slot]["multiple"] and len(resolved) != 1:
            raise OutputUnavailable(f"Input {slot} needs one file, but its output binding supplied {len(resolved)}.")
        paths, hashes = zip(*resolved)
        inputs[slot] = list(paths) if specs[slot]["multiple"] else paths[0]
        digests[slot] = list(hashes)
    if isolated:
        from .broker import create_plan
        result = create_plan(root, step["pipeline"], inputs, step["params"], step["cores"], step["timeout"], access=access)
    else:
        result = service.plan(root, step["pipeline"], inputs, step["params"], step["cores"], step["timeout"])
    if "plan_id" not in result:
        raise ValueError(f"Pipeline could not be planned ({result['status']}).")
    job_id, job_plan = result["plan_id"], result["plan"]
    actual = {slot: [file["sha256"] for file in records] for slot, records in job_plan["inputs"].items()}
    if actual != digests or job_plan["definition_sha256"] != step["definition_sha256"]:
        _job(root, "cancel", job_id, access=access, isolated=isolated)
        raise ValueError("A planned input or upstream output changed. Create a new workflow plan.")
    return job_id


def _record_job(root, step, value, access, isolated):
    state = value["status"]
    if state == "planned":
        # A launch claim survived but the engine has no durable submission.
        # Do not submit again because the previous worker may have started.
        _job(root, "cancel", step["job_id"], access=access, isolated=isolated)
        step.update(status="interrupted", error=step.get("error") or "Pipeline launch was interrupted.")
    elif state == "succeeded":
        try:
            result = _job(root, "results", step["job_id"], access=access, isolated=isolated)
            if result.get("warning") and not result.get("files"):
                step.update(status="failed", error=result["warning"])
                return
            files = []
            for item in result["files"]:
                provenance = item.get("pipeline_result", {})
                files.append({"output_name": provenance.get("output_name", item["name"]),
                              "kind": provenance.get("output_kind", item.get("kind", "file")),
                              "workspace_path": item["workspace_path"], "size": item["size"],
                              "sha256": item.get("sha256"), "remote": bool(item.get("remote"))})
            step.update(status=state, files=files, bundle_path=result.get("bundle_path"))
            step.pop("error", None)
        except (ValueError, OSError) as exc:
            step.update(status="failed", error=f"Output verification failed: {exc}")
    else:
        step["status"] = state
        if value.get("error"):
            step["error"] = value["error"]
        else:
            step.pop("error", None)


def _launch(root, workflow, step, store, access, isolated):
    try:
        if "job_id" not in step:
            step["job_id"] = _create_job(root, workflow, step, access, isolated)
        step["status"] = "launching"
        store.save(workflow)
        result = _job(root, "run", step["job_id"], access=access, isolated=isolated)
    except CapacityReached:
        # The engine raised before claiming the job. Its saved plan can wait.
        step["status"] = "waiting"
    except OutputUnavailable as exc:
        step.update(status="blocked", error=str(exc))
    except AuthError:
        raise
    except Exception as exc:
        step["error"] = str(exc)
        if step["status"] != "launching":
            step["status"] = "failed"
        # Reconcile any uncertain submission using its recorded job ID.
    else:
        _record_job(root, step, result, access, isolated)
    store.save(workflow)


def _cancel_jobs(root, workflow, access, isolated):
    for step in workflow["steps"].values():
        if step["status"] in STEP_DONE:
            continue
        if "job_id" not in step:
            step["status"] = "cancelled"
            continue
        try:
            value = _job(root, "cancel", step["job_id"], access=access, isolated=isolated)
            _record_job(root, step, value, access, isolated)
        except AuthError:
            raise
        except (ValueError, OSError) as exc:
            step.update(status="cancelling", error=f"Cancellation could not be confirmed: {exc}")
    states = {step["status"] for step in workflow["steps"].values()}
    if states <= STEP_DONE:
        workflow["status"] = "interrupted" if "interrupted" in states else "cancelled"


def _tick(root, workflow, store, access, isolated):
    workflow["status"] = "running"
    graph = workflow["steps"]
    for step in graph.values():
        if step["status"] in STEP_DONE | {"waiting"}:
            continue
        value = _job(root, "status", step["job_id"], access=access, isolated=isolated)
        _record_job(root, step, value, access, isolated)
    active = sum(step["status"] not in STEP_DONE | {"waiting"} for step in graph.values())
    for step in graph.values():
        if step["status"] != "waiting":
            continue
        dependencies = [graph[key] for key in step["depends_on"]]
        failed = [item["id"] for item in dependencies if item["status"] in STEP_DONE - {"succeeded"}]
        if failed:
            step.update(status="blocked", error="Prerequisites did not complete successfully: " + ", ".join(failed))
        elif active < MAX_PARALLEL and all(item["status"] == "succeeded" for item in dependencies):
            _launch(root, workflow, step, store, access, isolated)
            active += step["status"] not in STEP_DONE | {"waiting"}
    if all(step["status"] in STEP_DONE for step in graph.values()):
        workflow["status"] = "succeeded" if all(step["status"] == "succeeded" for step in graph.values()) else "failed"


def advance(root, identifier, *, access, isolated):
    root = _session(root, access)
    store = WorkflowStore(access)
    with store.lock(identifier):
        workflow = store.get(root.name, identifier)
        if workflow["status"] in ACTIVE:
            _check_backend(workflow, isolated)
            if workflow["status"] == "cancelling":
                _cancel_jobs(root, workflow, access, isolated)
            else:
                _tick(root, workflow, store, access, isolated)
            store.save(workflow)
        return _public(workflow)


def cancel(root, identifier, *, access, isolated):
    root = _session(root, access)
    store = WorkflowStore(access)
    with store.lock(identifier):
        workflow = store.get(root.name, identifier)
        if workflow["status"] in ACTIVE | {"planned"}:
            _check_backend(workflow, isolated)
            # Persist cancellation before attempting any backend aborts.
            workflow["status"] = "cancelling"
            store.save(workflow)
            _cancel_jobs(root, workflow, access, isolated)
            store.save(workflow)
        return _public(workflow)


def dispatch(root, args, *, access, isolated):
    if args.operation == "workflow-plan":
        return plan(root, args.steps, access=access, isolated=isolated)
    if args.operation == "workflow-list":
        root = _session(root, access)
        return {"workflows": [_summary(row) for row in WorkflowStore(access).list(root.name)]}
    if args.operation == "workflow-status":
        return status(root, args.workflow_id, access=access)
    operation = {"workflow-run": start, "workflow-cancel": cancel}[args.operation]
    return operation(root, args.workflow_id, access=access, isolated=isolated)


def start_reconciler(access, *, isolated):
    """Keep approved workflows moving after disconnects and application restarts."""
    stopped = Event()
    store = WorkflowStore(access)

    def poll():
        while not stopped.is_set():
            try:
                for record in store.active():
                    if stopped.is_set():
                        break
                    if record["isolated"] != isolated:
                        continue
                    try:
                        with principal_scope(Principal(record["owner"])):
                            root = access.workspace(record["session_id"])
                            advance(root, record["workflow_id"], access=access, isolated=isolated)
                    except AccessDenied:
                        # A deleted session cannot initiate further work.
                        continue
                    except Exception:
                        log.exception("Could not advance workflow %s", record["workflow_id"])
            except sqlite3.Error:
                log.exception("Could not load active workflows")
            stopped.wait(2)

    Thread(target=poll, name="pipeline-workflow-reconciliation", daemon=True).start()
    return stopped
