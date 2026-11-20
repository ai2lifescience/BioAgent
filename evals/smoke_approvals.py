"""Offline SDK approval, restart, isolation, and HTTP regression tests."""
from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import SQLiteSession
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from openai.types.responses.response_function_shell_tool_call import ResponseFunctionShellToolCall
from harness import runtime
from harness import sandbox
from harness.sessions import SessionMetadataStore
from harness.jobs import RunQueue
from interfaces import api, web

pipeline_module = importlib.import_module("tools.agent_tools.specialist.pipeline.pipeline_shell")


def response(text="Completed."):
    return ModelStep(output=[assistant_message(text)])


def pipeline(call_id="pipeline-1", job_id="a" * 32):
    return ResponseFunctionShellToolCall(
        id=f"item-{call_id}", call_id=call_id, type="shell_call", status="completed",
        action={"commands": [f"agent-pipeline cancel --job-id {job_id}"],
                "timeout_ms": None, "max_output_length": None},
    )


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SessionMetadataStore(self.root / "metadata")
        for attr, value in {
            "STATE_STORE": self.store,
            "SESSION_DB": self.root / "conversation.sqlite3",
        }.items():
            patcher = patch.object(runtime, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(sandbox, "WORKSPACES_DIR", self.root / "sessions")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(pipeline_module, "dispatch", return_value={"status": "ok", "value": "fixture"})
        self.workflow = patcher.start()
        self.addCleanup(patcher.stop)

    def pause(self, calls=None, session="test", steps=None):
        if steps is None:
            steps = [
                ModelStep(output=[function_call("pipeline_specialist", {"task": "Run the fixture pipeline"}, call_id="specialist")]),
                ModelStep(output=calls or [pipeline()]),
            ]
        result = asyncio.run(runtime.async_run_agent(
            "Run the fixture pipeline", session_id=session,
            model=ScriptedModel(steps),
        ))
        self.assertEqual(result["status"], "pending_approval", result["answer"])
        return result

    def resume(self, pending, approved=True, steps=None):
        return asyncio.run(runtime.async_resume_agent(
            pending["session_id"], approved, pending["approvals"][0]["approval_id"],
            model=ScriptedModel(steps or [response("Specialist finished."), response()]),
        ))

    def test_restart_approval_executes_once_and_preserves_history(self):
        pending = self.pause()
        self.workflow.assert_not_called()
        self.assertEqual(pending["approvals"][0]["tool_name"], "pipeline_shell")
        self.assertEqual(pending["approvals"][0]["arguments"]["commands"][0].split()[0], "agent-pipeline")
        # Recreate the metadata store, context, agents, and model as after restart.
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        result = self.resume(pending)
        self.assertEqual(result["status"], "ok", result["answer"])
        self.workflow.assert_called_once()
        self.assertEqual(result["run"]["run_id"], pending["run"]["run_id"])
        metadata = runtime.STATE_STORE.get_session("test").metadata
        self.assertNotIn("pending_run", metadata)
        self.assertEqual(metadata["message_count"], 2)
        sdk_session = SQLiteSession("test", db_path=runtime.SESSION_DB)
        try:
            items = asyncio.run(sdk_session.get_items())
        finally:
            sdk_session.close()
        self.assertEqual(sum(i.get("role") == "user" for i in items), 1)
        self.assertEqual(sum(i.get("type") == "function_call_output" for i in items), 1)
        with self.assertRaises(ValueError):
            self.resume(pending)
        self.workflow.assert_called_once()

    def test_rejection_never_executes_tool(self):
        result = self.resume(self.pause(), approved=False)
        self.assertEqual(result["status"], "ok", result["answer"])
        self.workflow.assert_not_called()

    def test_queue_keeps_original_review_when_approval_is_consumed(self):
        for approved in [True, False]:
            queue = RunQueue(self.root / f"reviews-{approved}.sqlite3")
            review = {"approval_id": "review", "tool_name": "pipeline_shell",
                      "arguments": {"commands": ["agent-pipeline run --plan-id fixture"]},
                      "plan": {"pipeline_name": "metagenomic_read_quality_control"}}
            with patch.object(queue, "dispatch"):
                run = queue.enqueue("Run quality control", "review-session", "fixture", 5)
                queue.update(run["run_id"], "pending_approval", result={"approvals": [review]})
                resumed = queue.resume("review-session", approved, "review")
                self.assertIsNone(resumed["result"])
                restored = RunQueue(queue.path)
                events = [event["payload"] for event in restored.events(run["run_id"])
                          if event["event"] == "approval_decision"]
                self.assertEqual(events, [{**review, "approved": approved}])
                self.assertIsNone(queue.resume("review-session", approved, "review"))

    def test_reviewed_plan_survives_progress_and_later_turn(self):
        pending = self.pause(steps=[ModelStep(output=[
            assistant_message("I will prepare the requested operation."),
            function_call("pipeline_specialist", {"task": "Run the fixture pipeline"}, call_id="specialist"),
        ]), ModelStep(output=[pipeline()])])
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        restored = api.list_session_messages("test")["pending_approval"]
        self.assertEqual(restored["approvals"], pending["approvals"])
        done = self.resume(pending)
        runtime.run_agent("Thanks", session_id="test", model=ScriptedModel([response("You're welcome.")]))
        # A later turn clears the last_approval fallback. The reviewed plan
        # must remain attached to its original result, not to the latest reply.
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        messages = api.list_session_messages("test")["messages"]
        completed = next(m for m in messages if m["text"] == done["answer"])
        self.assertEqual(completed.get("result"), done)
        self.assertNotIn("approval_decision", (messages[-1].get("result") or {}))

    def test_wrong_stale_and_cross_session_ids_do_not_consume_state(self):
        pending = self.pause()
        token = pending["approvals"][0]["approval_id"]
        for session, approved, approval_id in [("test", True, "wrong"), ("other", True, token), ("test", "false", token)]:
            with self.assertRaises(ValueError):
                asyncio.run(runtime.async_resume_agent(session, approved, approval_id, model=ScriptedModel()))
        with self.assertRaises(ValueError):
            asyncio.run(runtime.async_run_agent("New request", session_id="test", model=ScriptedModel()))
        self.assertIn("pending_run", self.store.get_session("test").metadata)
        self.workflow.assert_not_called()
        self.assertEqual(self.resume(pending)["status"], "ok")

    def test_multiple_nested_calls_require_each_approval_and_execute_once(self):
        calls = [pipeline("one"), pipeline("two", "b" * 32)]
        first = self.pause(calls)
        self.assertEqual(len(first["approvals"]), 2)
        second = self.resume(first, steps=[])
        self.assertEqual(second["status"], "pending_approval", second["answer"])
        self.assertEqual(len(second["approvals"]), 1)
        self.workflow.assert_not_called()
        done = self.resume(second)
        self.assertEqual(done["status"], "ok", done["answer"])
        self.assertCountEqual([call.args[1] for call in self.workflow.call_args_list],
                              [call.action.commands[0] for call in calls])

    def test_nested_specialist_approval_restores_shared_context(self):
        pending = self.pause(steps=[
            ModelStep(output=[function_call("pipeline_specialist", {"task": "Run the fixture pipeline"}, call_id="specialist")]),
            ModelStep(output=[pipeline()]),
        ])
        done = self.resume(pending, steps=[response("Specialist finished."), response("Root finished.")])
        self.assertEqual(done["status"], "ok", done["answer"])
        self.assertEqual(done["answer"], "Root finished.")
        self.workflow.assert_called_once()
        self.assertTrue(any(e["event"] == "approval_decision" for e in done["trace"]))
        self.assertIn("pipeline_shell", done["evidence"]["tools"])

    def test_saved_root_approval_resumes_without_exposing_shell_to_model(self):
        current_builder = runtime.create_agent

        def previous_agent(*args, **kwargs):
            agent = current_builder(*args, **kwargs)
            agent.tools.append(pipeline_module.pipeline_shell)
            return agent

        with patch.object(runtime, "create_agent", side_effect=previous_agent):
            pending = self.pause(steps=[ModelStep(output=[pipeline()])])
        self.assertEqual(pending["approvals"][0]["agent"], "Pipeline2Agent")
        self.workflow.assert_not_called()

        def completed(call):
            self.assertNotIn("pipeline_shell", {tool.name for tool in call.tools})
            return [assistant_message("Cancellation completed.")]

        done = self.resume(pending, steps=[ModelStep.respond(completed)])
        self.assertEqual(done["status"], "ok", done["answer"])
        self.assertEqual(done["answer"], "Cancellation completed.")
        self.workflow.assert_called_once()

    def test_http_requires_explicit_boolean_and_can_reject(self):
        pending = self.pause()
        server = ThreadingHTTPServer(("127.0.0.1", 0), web.AgentRequestHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        opener = build_opener(ProxyHandler({}))
        url = f"http://127.0.0.1:{server.server_port}/approve"
        def post(payload):
            req = Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with opener.open(req, timeout=10) as resp:
                return json.load(resp)
        payload = {"session_id": "test", "approval_id": pending["approvals"][0]["approval_id"]}
        for bad in [payload, {**payload, "approved": "false"}]:
            with self.assertRaises(HTTPError) as failure:
                post(bad)
            self.assertEqual(failure.exception.code, 400)
        def handler(session_id, approved, approval_id, **kwargs):
            model = ScriptedModel([response("Specialist finished."), response()])
            return asyncio.run(runtime.async_resume_agent(session_id, approved, approval_id, model=model))
        with patch.object(web, "handle_approval", side_effect=handler):
            result = post({**payload, "approved": False})
        self.assertEqual(result["status"], "ok")
        self.workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
