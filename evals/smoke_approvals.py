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
from interfaces import web

pipeline_module = importlib.import_module("tools.infrastructure.sdk_adapters.pipeline_shell")


def response(text="Completed."):
    return ModelStep(output=[assistant_message(text)])


def pipeline(call_id="pipeline-1"):
    return ResponseFunctionShellToolCall(
        id=f"item-{call_id}", call_id=call_id, type="shell_call", status="completed",
        action={"commands": ["agent-pipeline cancel --job-id " + "a" * 32],
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
        result = asyncio.run(runtime.async_run_agent(
            "Run the fixture pipeline", session_id=session,
            model=ScriptedModel(steps or [ModelStep(output=calls or [pipeline()])]),
        ))
        self.assertEqual(result["status"], "pending_approval", result["answer"])
        return result

    def resume(self, pending, approved=True, steps=None):
        return asyncio.run(runtime.async_resume_agent(
            pending["session_id"], approved, pending["approvals"][0]["approval_id"],
            model=ScriptedModel(steps or [response()]),
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
        self.assertEqual(sum(i.get("type") == "shell_call_output" for i in items), 1)
        with self.assertRaises(ValueError):
            self.resume(pending)
        self.workflow.assert_called_once()

    def test_rejection_never_executes_tool(self):
        result = self.resume(self.pause(), approved=False)
        self.assertEqual(result["status"], "ok", result["answer"])
        self.workflow.assert_not_called()

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

    def test_multiple_calls_pause_again_without_replaying_first(self):
        first = self.pause([pipeline("one"), pipeline("two")])
        self.assertEqual(len(first["approvals"]), 2)
        second = self.resume(first, steps=[])
        self.assertEqual(second["status"], "pending_approval", second["answer"])
        self.assertEqual(len(second["approvals"]), 1)
        self.workflow.assert_called_once()
        done = self.resume(second)
        self.assertEqual(done["status"], "ok", done["answer"])
        self.assertEqual(self.workflow.call_count, 2)

    def test_nested_specialist_approval_restores_shared_context(self):
        pending = self.pause(steps=[
            ModelStep(output=[function_call("pipeline_specialist", {"input": "Run the fixture pipeline"}, call_id="specialist")]),
            ModelStep(output=[pipeline()]),
        ])
        done = self.resume(pending, steps=[response("Specialist finished."), response("Root finished.")])
        self.assertEqual(done["status"], "ok", done["answer"])
        self.assertEqual(done["answer"], "Root finished.")
        self.workflow.assert_called_once()
        self.assertTrue(any(e["event"] == "approval_decision" for e in done["trace"]))
        self.assertIn("pipeline_shell", done["evidence"]["tools"])

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
            return asyncio.run(runtime.async_resume_agent(session_id, approved, approval_id, model=ScriptedModel([response()])))
        with patch.object(web, "handle_approval", side_effect=handler):
            result = post({**payload, "approved": False})
        self.assertEqual(result["status"], "ok")
        self.workflow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
