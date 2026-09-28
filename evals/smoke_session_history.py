"""Offline checks for server-owned conversation history and workspace sessions."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import SQLiteSession
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from harness import runtime, sandbox
from harness.contracts import normalize_run_result
from harness.sessions import SessionMetadataStore, _has_renderable_result
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
        first = runtime.run_agent(
            "Hello", session_id="rich_history",
            model=ScriptedModel([ModelStep(output=[assistant_message("Hi")])]),
        )
        self.assertEqual(first["result_contract_version"], 1)
        self.assertEqual(first["workspace_files"], first["files"])
        self.assertIsInstance(first["artifacts"], list)
        runtime.run_agent(
            "Analyze ACGT", session_id="rich_history",
            model=ScriptedModel([
                ModelStep(output=[function_call("sequence_stats", {
                    "source": {"sequence": "ACGT", "path": None, "sequence_type": "auto"},
                    "max_records": 100}, call_id="stats")]),
                ModelStep(output=[assistant_message("Sequence statistics complete.")]),
            ]),
        )
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        messages = api.list_session_messages("rich_history")["messages"]
        self.assertIsNone(messages[1].get("result"))
        self.assertEqual(messages[3]["result"]["evidence"]["tools"], ["sequence_stats"])

    def test_public_result_contract_separates_workspace_and_artifacts(self):
        payload = normalize_run_result({
            "answer": "Rendered.",
            "status": "ok",
            "session_id": "contract",
            "workspace_files": [{"path": "outputs/old.pdb"}],
            "artifacts": [{"path": "outputs/new.pdb", "kind": "structure"}],
        })
        self.assertEqual(payload["result_contract_version"], 1)
        self.assertEqual(payload["workspace_files"], [{"path": "outputs/old.pdb"}])
        self.assertEqual(payload["artifacts"], [{"path": "outputs/new.pdb", "kind": "structure"}])
        self.assertEqual(payload["files"], payload["workspace_files"])
        self.assertTrue(_has_renderable_result(payload))

    def test_progress_messages_do_not_consume_final_results(self):
        result = runtime.run_agent(
            "Analyze ACGT", session_id="progress",
            model=ScriptedModel([
                ModelStep(output=[
                    assistant_message("I will inspect the sequence first."),
                    function_call("sequence_stats", {
                        "source": {"sequence": "ACGT", "path": None, "sequence_type": "auto"},
                        "max_records": 100}, call_id="stats"),
                ]),
                ModelStep(output=[assistant_message("Sequence statistics complete.")]),
            ]),
        )
        self.assertEqual(result["status"], "ok", result["answer"])
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        messages = api.list_session_messages("progress")["messages"]
        self.assertEqual(len(messages), 3)
        self.assertNotIn("result", messages[1])
        self.assertEqual(messages[2].get("result"), result)

    def test_viewers_and_approval_records_survive_mixed_history(self):
        session = runtime.STATE_STORE.create_session(session_id="panels")
        items = [
            {"role": "user", "content": "An older request without a saved result"},
            {"role": "assistant", "content": "An older answer"},
        ]
        results = [
            {"files": [{"kind": "genome_map", "path": "outputs/genome_map.json"}],
             "evidence": {"tools": ["genome_render_map"]}},
            {"files": [{"kind": "structure", "path": "outputs/example.pdb"}],
             "evidence": {"tools": ["structure_inspect"]}},
            {"approval_decision": {"approved": True, "tool_name": "pipeline_shell",
                                   "arguments": {"commands": ["fixture"]}, "plan": {"name": "fixture"}}},
            {"approval_decision": {"approved": False, "tool_name": "shell",
                                   "arguments": {"commands": ["python example.py"]}}},
        ]
        for index, result in enumerate(results):
            request = f"Request {index}"
            # Identical answers must still be associated with the right request.
            result.update(answer="Done.\n", session_id="panels", status="ok")
            items.extend([
                {"role": "user", "content": request},
                {"role": "assistant", "content": "Checking the files."},
                {"role": "assistant", "content": "Done.\n"},
            ])
            runtime.STATE_STORE.record_exchange(session, request, result["answer"], result)
        items.extend([
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome."},
        ])
        # A normal answer still sees the persistent workspace, but those files
        # are not evidence produced by this answer and must not make it rich.
        runtime.STATE_STORE.record_exchange(session, "Thanks", "You're welcome.", {
            "answer": "You're welcome.",
            "files": [{"kind": "structure", "path": "outputs/example.pdb"}],
            "evidence": {"tools": []},
        })
        sdk_session = SQLiteSession("panels", db_path=runtime.SESSION_DB)
        try:
            asyncio.run(sdk_session.add_items(items))
        finally:
            sdk_session.close()
        runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
        messages = api.list_session_messages("panels")["messages"]
        self.assertEqual([m["result"] for m in messages if m.get("result")], results)
        self.assertNotIn("result", messages[1])
        self.assertNotIn("result", messages[-1])


if __name__ == "__main__":
    unittest.main()
