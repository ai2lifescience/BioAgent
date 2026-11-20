"""Structured graph planning, validation, approval and execution through the SDK."""
import asyncio
import json
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agents import AgentOutputSchema
from agents.tool_context import ToolContext
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from auth import AccessDenied, Principal, principal_scope
from harness import runtime, sandbox
from harness.context import AgentRunContext
from harness.sessions import SessionMetadataStore
from tools.agent_tools.specialist.pipeline import autograph
from tools.agent_tools.specialist.pipeline.graph_contracts import GraphProposal
from tools.infrastructure.pipeline_engine import service, workflow
from evals.test_pipeline_workflow import shell_call


def proposal():
    first = {"id": "prepare", "pipeline": "template_shell", "inputs": [
        {"slot": "reads", "sources": [{"path": "uploads/words.txt"}], "reason": "Normalize the uploaded text."},
        {"slot": "metadata", "sources": [{"path": "uploads/labels.tsv"}], "reason": "Use the matching labels."},
    ], "params": [], "cores": 1, "timeout": None, "depends_on": [], "reason": "Prepare normalized text."}
    second = {**first, "id": "summarize", "inputs": [
        {"slot": "reads", "sources": [{"step": "prepare", "output": "normalized_text"}],
         "reason": "Consume the verified normalized output from prepare."},
        first["inputs"][1],
    ], "reason": "Process the prepared text with the same labels."}
    return {"status": "ready", "summary": "Normalize text and process its verified output.",
            "steps": [second, first], "missing_requirements": [], "assumptions": []}


class AutographTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        state = SessionMetadataStore(self.base / "metadata")
        for obj, name, value in ((runtime, "STATE_STORE", state),
                                 (runtime, "SESSION_DB", self.base / "history.sqlite3"),
                                 (sandbox, "WORKSPACES_DIR", self.base / "workspaces")):
            change = patch.object(obj, name, value)
            change.start()
            self.addCleanup(change.stop)
        with state.locked_session("autograph", "Test graph planning") as (session, _):
            self.session = session
            sandbox.prepare_run(session)
        self.root = sandbox.session_root("autograph")
        (self.root / "uploads").mkdir(parents=True)
        (self.root / "uploads/words.txt").write_text("alpha\nbeta\n")
        (self.root / "uploads/labels.tsv").write_text("sequence_id\tsubtype\nseq_1\tone\nseq_2\ttwo\n")

    def test_structured_schema_and_internal_read_only_tools(self):
        self.assertTrue(AgentOutputSchema(GraphProposal).is_strict_json_schema())
        model = GraphProposal.model_validate(proposal())
        self.assertEqual(model.steps[0].command_step()["inputs"]["reads"],
                         {"step": "prepare", "output": "normalized_text"})
        self.assertEqual(autograph.build_autograph(ScriptedModel()).name, "autograph_specialist")

    def test_planner_proposal_reaches_sdk_approval_and_real_fixture_execution(self):
        def planner_turn(call):
            self.assertEqual({tool.name for tool in call.tools}, {"autograph_catalog", "autograph_files"})
            replies = {item["call_id"]: json.loads(item["output"])["data"]
                       for item in call.input if isinstance(item, dict) and item.get("type") == "function_call_output"}
            contract, = replies["catalog"]["pipelines"]
            self.assertEqual(contract["outputs"]["normalized_text"]["kind"], "text")
            self.assertTrue(contract["inputs"]["reads"]["required"])
            self.assertEqual(contract["plan_limits"], {"max_cores": 4, "max_timeout_seconds": 120})
            self.assertEqual({item["workspace_path"] for item in replies["files"]["files"]},
                             {"uploads/words.txt", "uploads/labels.tsv"})
            self.assertTrue(all(item["available_locally"] for item in replies["files"]["files"]))
            return [assistant_message(json.dumps(proposal()))]

        def save_proposal(call):
            item = next(item for item in call.input if isinstance(item, dict)
                        and item.get("type") == "function_call_output" and item.get("call_id") == "design")
            value = json.loads(item["output"])["data"]
            self.assertEqual(value["status"], "ready")
            self.assertEqual([step["id"] for step in value["steps"]], ["prepare", "summarize"])
            command = shlex.join(("agent-pipeline", "workflow-plan", "--steps", json.dumps(value["steps"])))
            return [shell_call(command, "save-graph")]

        def request_approval(call):
            saved, = workflow.WorkflowStore(sandbox.execution_access()).list("autograph")
            return [shell_call(f"agent-pipeline workflow-run --workflow-id {saved['workflow_id']}", "start-graph")]

        model = ScriptedModel([
            ModelStep(output=[function_call("pipeline_specialist", {"task": "Run the two-step text fixture."}, call_id="pipeline")]),
            ModelStep(output=[function_call("autograph_specialist", {"task": "Design the two-step text fixture."}, call_id="design")]),
            ModelStep(output=[function_call("autograph_catalog", {"pipeline": "template_shell", "offset": 0, "limit": 8}, call_id="catalog"),
                              function_call("autograph_files", {"prefix": "uploads/", "offset": 0, "limit": 50}, call_id="files")]),
            ModelStep.respond(planner_turn), ModelStep.respond(save_proposal), ModelStep.respond(request_approval),
        ])
        pending = asyncio.run(runtime.async_run_agent("Run the text fixture demonstration.", session_id="autograph", model=model))
        self.assertEqual(pending["status"], "pending_approval", pending["answer"])
        self.assertNotIn("autograph_specialist", {tool.name for tool in model.calls[0].tools})
        self.assertEqual({tool.name for tool in model.calls[1].tools}, {"pipeline_shell", "autograph_specialist"})
        review = pending["approvals"][0]
        self.assertEqual(review["agent"], "pipeline_specialist")
        self.assertIn("verified normalized output", review["plan"]["steps"][1]["input_reasons"]["reads"])
        self.assertEqual(service.JobStore(self.root).list(), [])
        self.assertIn("autograph_catalog", pending["evidence"]["tools"])
        resumed = ScriptedModel([ModelStep(output=[assistant_message(text)]) for text in
                                 ("Workflow launched.", "Waiting for verified outputs.", "The two-step workflow succeeded.")])
        result = asyncio.run(runtime.async_resume_agent("autograph", True, review["approval_id"], model=resumed))
        self.assertEqual(result["status"], "ok", result["answer"])
        self.assertEqual(result["answer"], "The two-step workflow succeeded.")
        self.assertTrue(any(event["event"] == "pipeline_workflow_completion_collected" for event in result["trace"]))
        self.assertEqual(len(service.JobStore(self.root).list()), 2)

    def check_incomplete_proposal(self, value):
        model = ScriptedModel([
            ModelStep(output=[function_call("pipeline_specialist", {"task": "Prepare the fixture analysis."}, call_id="pipeline")]),
            ModelStep(output=[function_call("autograph_specialist", {"task": "Design the requested graph."}, call_id="design")]),
            ModelStep(output=[assistant_message(json.dumps(value))]),
            ModelStep(output=[assistant_message("The plan needs attention.")]),
            ModelStep(output=[assistant_message("Please provide the missing information.")]),
        ])
        result = asyncio.run(runtime.async_run_agent("Prepare a fixture plan.", session_id="autograph", model=model))
        self.assertEqual(result["status"], "ok", result["answer"])
        self.assertFalse(result["approval_required"])
        self.assertEqual(workflow.WorkflowStore(sandbox.execution_access()).list("autograph"), [])
        self.assertEqual(service.JobStore(self.root).list(), [])
        return result

    def test_missing_requirements_return_to_coordinator_without_saving_or_launching(self):
        value = {"status": "needs_input", "summary": "A matching label file is required.", "steps": [],
                 "missing_requirements": ["Provide the label file for these text records."], "assumptions": []}
        result = self.check_incomplete_proposal(value)
        self.assertIn("autograph_specialist", result["evidence"]["tools"])

    def test_invalid_output_reference_is_rejected_before_coordinator_can_save_it(self):
        value = proposal()
        value["steps"][0]["inputs"][0]["sources"][0]["output"] = "invented_output"
        result = self.check_incomplete_proposal(value)
        self.assertTrue(any("does not declare output" in str(item) for item in result["evidence"]["tool_errors"]))

    def test_catalog_checks_session_ownership_before_discovery(self):
        context = AgentRunContext(session=self.session, model_key="fixture")
        with principal_scope(Principal("another-owner")):
            with self.assertRaises(AccessDenied):
                autograph._owned_workspace(context)

    def test_ready_proposal_can_describe_a_single_pipeline(self):
        value = proposal()
        value["steps"] = value["steps"][1:]
        result = GraphProposal.model_validate(value)
        from tools.infrastructure.pipeline_engine import dependency_graph
        graph, _ = dependency_graph.build(self.root, [result.steps[0].command_step()], isolated=False, allow_single=True)
        self.assertEqual(list(graph), ["prepare"])
        with self.assertRaisesRegex(ValueError, "between 2"):
            workflow.plan(self.root, [result.steps[0].command_step()], access=sandbox.execution_access(), isolated=False)

    def test_remote_results_are_identified_as_requiring_import(self):
        context = AgentRunContext(session=self.session, model_key="fixture")
        remote = {"workspace_path": "pipeline-artifacts/fixture/0/output.txt", "name": "output.txt", "remote": True,
                  "pipeline_result": {"pipeline_name": "template_shell", "output_name": "normalized_text"}}
        with patch.object(autograph, "isolated_execution", return_value=True), \
             patch.object(autograph.broker, "remote_files", return_value=[remote]), \
             patch.object(autograph.broker, "materialize") as materialize:
            arguments = json.dumps({"prefix": "pipeline-artifacts/", "offset": 0, "limit": 50})
            tool_context = ToolContext(context=context, tool_name="autograph_files", tool_call_id="files", tool_arguments=arguments)
            raw = asyncio.run(autograph.autograph_files.on_invoke_tool(tool_context, arguments))
        entry, = json.loads(raw)["data"]["files"]
        self.assertFalse(entry["available_locally"])
        self.assertEqual(entry["pipeline_result"]["output_name"], "normalized_text")
        materialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
