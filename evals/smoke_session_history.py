"""Offline checks for server-owned conversation history and workspace sessions."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from harness import runtime, sandbox
from harness.sessions import SessionMetadataStore
from interfaces import api


class SessionHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for module, name, value in (
            (runtime, "STATE_STORE", SessionMetadataStore(self.root / "metadata")),
            (runtime, "SESSION_DB", self.root / "conversation.sqlite3"),
            (sandbox, "WORKSPACES_DIR", self.root / "workspaces"),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_sdk_history_survives_application_restart_and_stays_session_scoped(self):
        result = runtime.run_agent(
            "Hello", session_id="first",
            model=ScriptedModel([ModelStep(output=[assistant_message("Hello back.")])]),
        )
        self.assertEqual(result["status"], "ok", result["answer"])
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        self.assertEqual(api.list_session_messages("first")["messages"], [
            {"role": "user", "text": "Hello"},
            {"role": "assistant", "text": "Hello back."},
        ])
        self.assertEqual(api.list_session_messages("other")["messages"], [])
        self.assertEqual(runtime.list_sessions()[0]["message_count"], 2)

    def test_history_exposes_pending_controls_without_private_run_snapshot(self):
        session = runtime.STATE_STORE.create_session(session_id="pending")
        approvals = [{"approval_id": "decision", "tool_name": "example", "arguments": {}}]
        session.metadata["pending_run"] = {"state": "private run snapshot", "approvals": approvals}
        runtime.STATE_STORE.save(session)
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        pending = api.list_session_messages("pending")["pending_approval"]
        self.assertEqual(pending["approvals"], approvals)
        self.assertTrue(pending["approval_required"])
        self.assertNotIn("state", pending)

    def test_upload_only_session_is_discoverable_after_restart(self):
        uploaded = api.write_workspace_file("uploads_only", "notes.txt", b"Saved input")
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        self.assertEqual(runtime.list_sessions()[0]["session_id"], "uploads_only")
        self.assertEqual(api.list_session_messages("uploads_only")["messages"], [])
        self.assertEqual(api.read_workspace_file("uploads_only", uploaded["workspace_path"]), b"Saved input")

    def test_structured_results_restore_after_reload(self):
        runtime.run_agent(
            "Hello", session_id="rich_history",
            model=ScriptedModel([ModelStep(output=[assistant_message("Hi")])]),
        )
        runtime.run_agent(
            "Analyze ACGT", session_id="rich_history",
            model=ScriptedModel([
                ModelStep(output=[function_call("sequence_analysis", {"sequence": "ACGT"}, call_id="stats")]),
                ModelStep(output=[assistant_message("Sequence statistics complete.")]),
            ]),
        )
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        messages = api.list_session_messages("rich_history")["messages"]
        self.assertIsNone(messages[1].get("result"))
        self.assertEqual(messages[3]["result"]["evidence"]["tools"], ["sequence_analyze"])


if __name__ == "__main__":
    unittest.main()
