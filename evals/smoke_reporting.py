"""SDK-native tests for evidence-bound review and report synthesis."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import Agent, Runner
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from harness.context import AgentRunContext
from harness.sessions import SessionMetadata
from harness.tracing import configure_tracing
from tools.agent_tools.reporting import build_report_review

configure_tracing()


class ReportingTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_is_a_structured_nested_agent_tool(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path = root / "evidence.json"
            evidence_path.write_text(json.dumps({
                "schema_version": 1,
                "sources": [{
                    "id": "ev_fixture",
                    "title": "Fixture source",
                    "url": "https://example.org/source",
                    "source": "fixture",
                    "text": "The sequence evidence supports a cautious conclusion.",
                    "retrieved_at": "2026-09-22T00:00:00+00:00",
                }],
            }), encoding="utf-8")
            context = AgentRunContext(
                session=SessionMetadata(session_id="report", metadata={"run": {"session_dir": directory, "workspace_dir": directory}}),
                model_key="fixture",
            )
            nested = ScriptedModel([ModelStep(output=[assistant_message(json.dumps({
                "assessment": "The evidence supports a cautious conclusion.",
                "source_ids": ["ev_fixture"],
                "limitations": ["Only one fixture source was supplied."],
            }))])])
            parent = ScriptedModel([
                ModelStep(output=[function_call("report_review", {
                    "question": "What does the sequence evidence show?",
                    "evidence_paths": ["evidence.json"],
                }, call_id="review-call")]),
                ModelStep(output=[assistant_message("Review completed.")]),
            ])
            agent = Agent(name="research", model=parent, tools=[build_report_review(nested)])
            result = await Runner.run(agent, "Review the evidence", context=context)
            self.assertEqual(result.final_output, "Review completed.")
            self.assertEqual(context.tool_results[0]["tool"], "report_review")
            self.assertEqual(context.tool_results[0]["result"]["source_ids"], ["ev_fixture"])
            self.assertIn("cautious", context.tool_results[0]["result"]["assessment"])


if __name__ == "__main__":
    unittest.main()
