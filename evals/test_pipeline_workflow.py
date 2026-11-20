"""Offline orchestration checks with synthetic text files and fixture jobs."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest import TestCase, skipUnless
from unittest.mock import patch

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from openai.types.responses.response_function_shell_tool_call import ResponseFunctionShellToolCall

from auth import AccessDenied, Principal, principal_scope
from harness import runtime, sandbox
from harness.sessions import SessionMetadataStore
from isolation import WorkspaceAccess
from tools.infrastructure.pipeline_engine import broker, service, workflow
from tools.infrastructure.pipeline_engine.commands import parse_command
from tools.infrastructure.pipeline_engine.store import CapacityReached
from tools.infrastructure.workspace.public import public_payload


def stage(identifier, reads="uploads/words.txt", **extra):
    return {"id": identifier, "pipeline": "template_shell",
            "inputs": {"reads": reads, "metadata": "uploads/labels.tsv"}, **extra}


def output(step):
    return {"step": step, "output": "normalized_text"}


def shell_call(command, call_id):
    return ResponseFunctionShellToolCall(id=f"item-{call_id}", call_id=call_id, type="shell_call", status="completed",
        action={"commands": [command], "timeout_ms": None, "max_output_length": None})


class WorkflowTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        state = SessionMetadataStore(self.base / "metadata")
        self.access = WorkspaceAccess(state.ownership, self.base / "workspaces")
        state.ownership.claim("fixture")
        self.root = self.access.workspace("fixture")
        (self.root / "uploads").mkdir(parents=True)
        (self.root / "uploads" / "words.txt").write_text("alpha\nbeta\n")
        (self.root / "uploads" / "labels.tsv").write_text("sequence_id\tsubtype\nseq_1\tone\nseq_2\ttwo\n")
        for obj, field, value in ((runtime, "STATE_STORE", state), (runtime, "SESSION_DB", self.base / "chat.sqlite3"),
                                  (sandbox, "WORKSPACES_DIR", self.access.workspaces_root)):
            patcher = patch.object(obj, field, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def command(self, *args):
        parsed = parse_command(shlex.join(("agent-pipeline", *args)))
        return workflow.dispatch(self.root, parsed, access=self.access, isolated=False)

    def plan(self, *steps):
        return self.command("workflow-plan", "--steps", json.dumps(steps))["workflow_id"]

    def tick(self, identifier):
        value = workflow.advance(self.root, identifier, access=self.access, isolated=False)
        return value, {step["id"]: step for step in value["steps"]}

    def test_rejects_invalid_dependencies_and_other_session(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.plan(stage("a", output("b")), stage("b", output("a")))
        with self.assertRaisesRegex(ValueError, "does not declare output"):
            self.plan(stage("a"), stage("b", {"step": "a", "output": "invented"}))
        with self.assertRaisesRegex(ValueError, "unknown step"):
            self.plan(stage("a"), stage("b", output("missing")))
        identifier = self.plan(stage("a"), stage("b", output("a")))
        with principal_scope(Principal("unrelated")):
            with self.assertRaises(AccessDenied):
                self.command("workflow-status", "--workflow-id", identifier)
        self.access.ownership.claim("other")
        with self.assertRaisesRegex(ValueError, "not found"):
            workflow.status(self.access.workspace("other"), identifier, access=self.access)
        self.assertEqual(service.JobStore(self.root).list(), [])

    def test_real_jobs_pass_verified_output_through_three_steps(self):
        identifier = self.plan(stage("finish", output("prepare")), stage("source"), stage("prepare", output("source")))
        self.assertEqual(self.tick(identifier)[0]["status"], "planned")
        self.assertEqual(service.JobStore(self.root).list(), [])
        self.command("workflow-run", "--workflow-id", identifier)
        first, steps = self.tick(identifier)
        self.assertEqual(first["status"], "running")
        self.assertNotIn("job_id", steps["prepare"])
        self.assertNotIn("job_id", steps["finish"])
        deadline = monotonic() + 20
        while first["status"] in workflow.ACTIVE and monotonic() < deadline:
            sleep(.05)
            first, steps = self.tick(identifier)
        self.assertEqual(first["status"], "succeeded", first)
        store = service.JobStore(self.root)
        self.assertEqual(len(store.list()), 3)
        for source, dest in (("source", "prepare"), ("prepare", "finish")):
            verified = next(item for item in steps[source]["files"] if item["output_name"] == "normalized_text")
            consumed = store.get(steps[dest]["job_id"])["plan"]["inputs"]["reads"][0]
            self.assertEqual(consumed["path"], verified["workspace_path"])
            self.assertEqual(consumed["sha256"], verified["sha256"])
            self.assertEqual(public_payload(consumed["path"], self.root), consumed["path"])
        self.command("workflow-run", "--workflow-id", identifier)
        self.assertEqual(self.tick(identifier)[0]["status"], "succeeded")
        self.assertEqual(len(store.list()), 3)

    @skipUnless(os.getenv("AGENT_TEST_DOCKER") == "1", "Set AGENT_TEST_DOCKER=1 to run real containers")
    def test_docker_jobs_pass_published_output_to_next_step(self):
        steps = [stage("a"), stage("b", output("a"))]
        identifier = workflow.plan(self.root, steps, access=self.access, isolated=True)["workflow_id"]
        workflow.start(self.root, identifier, access=self.access, isolated=True)
        deadline = monotonic() + 30
        while monotonic() < deadline:
            result = workflow.advance(self.root, identifier, access=self.access, isolated=True)
            if result["status"] not in workflow.ACTIVE:
                break
            sleep(.1)
        self.assertEqual(result["status"], "succeeded", result)
        upstream, downstream = result["steps"]
        public = next(item for item in upstream["files"] if item["output_name"] == "normalized_text")
        state = broker.get_plan(self.root, downstream["job_id"], access=self.access)["plan"]
        self.assertEqual(state["public_inputs"]["reads"], public["workspace_path"])
        self.assertEqual(state["inputs"]["reads"][0]["sha256"], public["sha256"])

    def test_parallel_jobs_and_failure_block_only_descendants(self):
        identifier = self.plan(stage("a"), stage("b"), stage("c", output("a")), stage("d", output("c")))
        self.command("workflow-run", "--workflow-id", identifier)
        store = service.JobStore(self.root)
        with patch.object(service, "start", side_effect=lambda root, job_id: store.update(job_id, status="running")) as start, \
             patch.object(service, "status", side_effect=lambda root, job_id: store.get(job_id)):
            _, steps = self.tick(identifier)
            self.assertEqual(start.call_count, 2)
            self.assertEqual([steps[key]["status"] for key in ("a", "b", "c", "d")],
                             ["running", "running", "waiting", "waiting"])
            store.update(steps["a"]["job_id"], status="failed", error="fixture failed")
            status, steps = self.tick(identifier)
            self.assertEqual(status["status"], "running")
            self.assertEqual([steps[key]["status"] for key in ("a", "b", "c", "d")],
                             ["failed", "running", "blocked", "blocked"])
            self.assertEqual(start.call_count, 2)
            result = self.command("workflow-cancel", "--workflow-id", identifier)
            self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.tick(identifier)[0]["status"], "cancelled")

    def test_waits_for_capacity_and_reconciles_existing_job_after_restart(self):
        identifier = self.plan(stage("a"), stage("b", output("a")))
        self.command("workflow-run", "--workflow-id", identifier)
        with patch.object(service, "start", side_effect=CapacityReached("fixture limit")):
            _, steps = self.tick(identifier)
        job_id = steps["a"]["job_id"]
        self.assertEqual(steps["a"]["status"], "waiting")
        store = service.JobStore(self.root)
        with patch.object(service, "start", side_effect=lambda root, job: store.update(job, status="running")) as start, \
             patch.object(service, "status", side_effect=lambda root, job: store.get(job)):
            # A chat worker and the background reconciler can race on the same job.
            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = (pool.submit(self.tick, identifier) for _ in range(2))
                first.result()
                second.result()
            start.assert_called_once_with(self.root, job_id)
            store.update(job_id, status="succeeded", result={"output_records": []})
            result, steps = self.tick(identifier)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(steps["b"]["status"], "blocked")
        self.assertIn("a.normalized_text", steps["b"]["error"])
        self.assertNotIn("job_id", steps["b"])

    def test_changed_input_is_rejected_before_any_launch(self):
        identifier = self.plan(stage("a"), stage("b", output("a")))
        (self.root / "uploads" / "words.txt").write_text("changed")
        self.command("workflow-run", "--workflow-id", identifier)
        with patch.object(service, "start") as start:
            status, steps = self.tick(identifier)
        start.assert_not_called()
        self.assertEqual(status["status"], "failed")
        self.assertIn("changed", steps["a"]["error"])
        self.assertEqual(steps["b"]["status"], "blocked")

    def test_interrupted_submission_claim_is_not_replayed(self):
        identifier = self.plan(stage("a"), stage("b", depends_on=["a"]))
        self.command("workflow-run", "--workflow-id", identifier)
        with patch.object(service, "start", side_effect=SystemExit("interruption")):
            with self.assertRaises(SystemExit):
                self.tick(identifier)
        with patch.object(service, "start") as start:
            result, steps = self.tick(identifier)
        start.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(steps["a"]["status"], "interrupted")
        self.assertEqual(steps["b"]["status"], "blocked")
        self.assertNotIn("job_id", steps["b"])

    def test_reconciler_continues_workflow_without_chat_worker(self):
        identifier = self.plan(stage("a"), stage("b", output("a")))
        self.command("workflow-run", "--workflow-id", identifier)
        self.tick(identifier)
        stop = workflow.start_reconciler(self.access, isolated=False)
        try:
            deadline = monotonic() + 20
            while monotonic() < deadline:
                result = self.command("workflow-status", "--workflow-id", identifier)
                if result["status"] not in workflow.ACTIVE:
                    break
                sleep(.05)
            self.assertEqual(result["status"], "succeeded", result)
            self.assertEqual(len(service.JobStore(self.root).list()), 2)
        finally:
            stop.set()

    def test_sdk_reviews_graph_and_collects_real_terminal_result(self):
        steps = [stage("a"), stage("b", output("a"))]
        command = shlex.join(("agent-pipeline", "workflow-plan", "--steps", json.dumps(steps)))

        def start_saved_workflow(call):
            self.assertIn("pipeline_shell", {tool.name for tool in call.tools})
            saved, = self.command("workflow-list")["workflows"]
            self.assertEqual(saved["status"], "planned")
            return [shell_call(f"agent-pipeline workflow-run --workflow-id {saved['workflow_id']}", "workflow-review")]

        model = ScriptedModel([
            ModelStep(output=[function_call("pipeline_specialist", {"task": "Run the two-step fixture workflow."},
                                            call_id="delegate-workflow")]),
            ModelStep(output=[shell_call(command, "workflow-plan")]),
            ModelStep.respond(start_saved_workflow),
        ])
        run = asyncio.run(runtime.async_run_agent("Run the text fixture workflow.", session_id="fixture", model=model))
        self.assertEqual(run["status"], "pending_approval", run)
        self.assertNotIn("pipeline_shell", {tool.name for tool in model.calls[0].tools})
        approval = run["approvals"][0]
        self.assertEqual(approval["agent"], "pipeline_specialist")
        self.assertEqual(approval["plan"]["steps"][1]["inputs"]["reads"], output("a"))
        self.assertEqual(service.JobStore(self.root).list(), [])

        def summarize_completed(call):
            self.assertNotIn("pipeline_shell", {tool.name for tool in call.tools})
            notice = next(item["content"] for item in call.input if isinstance(item, dict)
                          and item.get("role") == "developer" and "pipeline_workflows" in str(item.get("content")))
            completed, = json.loads(notice.split("\n", 1)[1])["pipeline_workflows"]
            self.assertEqual(completed["status"], "succeeded")
            return [assistant_message("The workflow finished.")]

        model = ScriptedModel([ModelStep(output=[assistant_message("Workflow launched.")]),
                               ModelStep(output=[assistant_message("Working.")]),
                               ModelStep.respond(summarize_completed)])
        run = asyncio.run(runtime.async_resume_agent("fixture", True, approval["approval_id"], model=model))
        self.assertEqual(run["status"], "ok", run)
        self.assertEqual(run["answer"], "The workflow finished.")
        self.assertTrue(any(event["event"] == "pipeline_workflow_completion_collected" for event in run["trace"]))
        self.assertTrue(any(path.endswith("normalized.txt") for path in run["evidence"]["files"]))

    def test_sdk_rejection_leaves_workflow_unapproved(self):
        identifier = self.plan(stage("a"), stage("b", output("a")))
        command = f"agent-pipeline workflow-run --workflow-id {identifier}"
        model = ScriptedModel([
            ModelStep(output=[function_call("pipeline_specialist", {"task": "Review the fixture workflow."},
                                            call_id="delegate-review")]),
            ModelStep(output=[shell_call(command, "workflow-review")]),
        ])
        run = asyncio.run(runtime.async_run_agent("Review the text fixture workflow.", session_id="fixture", model=model))
        approval = run["approvals"][0]
        model = ScriptedModel([ModelStep(output=[assistant_message("Approval declined.")]),
                               ModelStep(output=[assistant_message("Workflow rejected.")])])
        run = asyncio.run(runtime.async_resume_agent("fixture", False, approval["approval_id"], model=model))
        self.assertEqual(run["status"], "ok", run)
        self.assertEqual(self.tick(identifier)[0]["status"], "planned")
        self.assertEqual(service.JobStore(self.root).list(), [])

    def test_isolated_handoff_materializes_remote_outputs_and_checks_hashes(self):
        steps = [stage("a"), stage("b", output("a")), stage("c", output("a"))]
        result = workflow.plan(self.root, steps, access=self.access, isolated=True)
        identifier = result["workflow_id"]
        workflow.start(self.root, identifier, access=self.access, isolated=True)
        private = self.access.metadata_root / ".pipelines" / self.root.name
        remote_jobs = service.JobStore(private)
        first = remote_jobs.create({"pipeline_name": "template_wdl"})["job_id"]
        remote_jobs.update(first, status="succeeded", result={"output_records": [
            {"name": "normalized_text", "path": "normalized.txt", "size": 3},
        ]})
        heads = {"job_id": first, "status": "succeeded", "files": [
            {"name": "normalized.txt", "size": 3, "workspace_path": f"pipeline-artifacts/{first}/0/normalized.txt",
             "remote": True, "pipeline_result": {"output_name": "normalized_text"}},
        ], "bundle_path": f"pipeline-bundles/{first}/results.zip"}
        current_plan = broker.create_plan

        class RecordingBroker:
            def __init__(self):
                self.jobs = []

            def dispatch(self, root, command, **kwargs):
                args = parse_command(command)
                if args.operation == "results":
                    return heads
                if args.operation == "run":
                    self.jobs.append(args.plan_id)
                    return {"status": "running"}
                return {"status": "succeeded"}

        fixture = RecordingBroker()
        with patch.object(broker, "dispatch", side_effect=fixture.dispatch), \
             patch.object(broker, "remote_stream") as stream, \
             patch.object(broker, "create_plan", wraps=current_plan) as plan:
            # The first job is an existing remote submission, with a saved ID.
            store = workflow.WorkflowStore(self.access)
            record = store.get(self.root.name, identifier)
            record["steps"]["a"].update(status="running", job_id=first)
            store.save(record)
            # Use the same validated byte stream and publication route as S3.
            stream.return_value.__enter__.return_value = ({"Body": io.BytesIO(b"abc")}, {})
            workflow.advance(self.root, identifier, access=self.access, isolated=True)
        self.assertEqual(len(fixture.jobs), 2)
        stream.assert_called_once()
        paths = [call.args[2]["reads"] for call in plan.call_args_list]
        self.assertEqual(paths[0], paths[1])
        self.assertEqual((self.root / paths[0]).read_bytes(), b"abc")
