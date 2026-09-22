"""Offline smoke checks for the Agents SDK Pipeline2Agent architecture."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from openai.types.responses.response_function_shell_tool_call import ResponseFunctionShellToolCall
from harness import runtime
from harness.agent import create_agent
from tools.agent_tools import (
    build_coding,
    build_data_analysis,
    build_document,
    build_pipeline,
    build_research,
)
from tools.function_tools import FUNCTION_TOOLS


def main() -> int:
    tools = list(FUNCTION_TOOLS)
    agent = create_agent("gpt-oss", model=ScriptedModel())
    names = {tool.name for tool in agent.tools}
    expected = {
        "sequence_stats", "sequence_find_orfs", "sequence_translate", "sequence_reverse_complement",
        "table_profile", "table_group", "table_plot", "structure_inspect",
        "genome_read_features", "genome_render_map", "pubmed_search", "web_search", "web_fetch", "evidence_index",
        "evidence_retrieve", "report_write", "database_lookup", "pdb_download",
        "alphafold_download", "file_inspection", "document_read", "workspace_search",
        "blast_search", "code_inspection", "code_edit", "code_test", "pipeline_shell",
        "research_specialist", "pipeline_specialist", "document_specialist",
        "data_analysis_specialist", "coding_specialist", "report_review", "report_synthesize",
    }
    assert expected <= names
    assert not {"biology_specialist", "retrieval_specialist", "web_research_specialist"} & names
    for specialist_name in {
        "research_specialist", "pipeline_specialist", "document_specialist",
        "data_analysis_specialist", "coding_specialist",
    }:
        specialist = next(tool for tool in agent.tools if tool.name == specialist_name)
        assert set(specialist.params_json_schema["properties"]) == {"task"}
    assert agent.name == "Pipeline2Agent"
    assert next(tool for tool in agent.tools if tool.name == "code_edit").needs_approval is False
    assert next(tool for tool in agent.tools if tool.name == "code_test").needs_approval is False
    specialist_builders = {
        build_pipeline: "pipeline_specialist",
        build_document: "document_specialist",
        build_data_analysis: "data_analysis_specialist",
        # The research specialist owns evidence collection and report synthesis.
        build_research: "research_specialist",
        build_coding: "coding_specialist",
    }
    assert {builder(ScriptedModel()).name for builder in specialist_builders} == set(specialist_builders.values())

    runtime.SESSION_DB = PROJECT_ROOT / "runtime" / "smoke_agents.sqlite3"
    model = ScriptedModel([
        ModelStep(output=[function_call("sequence_stats", {"source": {"sequence": "ACGT", "path": None, "sequence_type": "auto"}, "max_records": 100}, call_id="call-1")]),
        ModelStep(output=[assistant_message("The sequence has 50% GC content.")]),
    ])
    result = asyncio.run(runtime.async_run_agent("Analyze ACGT", session_id="smoke_agents", model=model))
    assert result["runtime"] == "agents_sdk"
    assert result["answer"] == "The sequence has 50% GC content."
    assert result["evidence"]["tools"] == ["sequence_stats"]
    assert any(event["event"] == "sdk_trace_started" for event in result["trace"])
    assert any(event["event"] == "guardrail_completed" for event in result["trace"])

    blocked = asyncio.run(runtime.async_run_agent(
        "Design a pathogen to increase infectivity", session_id="smoke_blocked", model=ScriptedModel()
    ))
    assert blocked["status"] == "blocked"
    assert any(event["event"] == "guardrail_blocked" for event in blocked["trace"])

    approval_model = ScriptedModel([
        ModelStep(output=[ResponseFunctionShellToolCall(
            id="approval-item", call_id="approval-call", type="shell_call", status="completed",
            action={"commands": ["agent-pipeline cancel --job-id " + "a" * 32],
                    "timeout_ms": None, "max_output_length": None},
        )]),
        ModelStep(output=[assistant_message("Pipeline approval completed.")]),
    ])
    pending = asyncio.run(runtime.async_run_agent(
        "Run the pipeline", session_id="smoke_approval", model=approval_model,
    ))
    assert pending["status"] == "pending_approval"
    assert pending["approval_required"] is True
    assert pending["approvals"][0]["call_id"] == "approval-call"
    resumed = asyncio.run(runtime.async_resume_agent(
        "smoke_approval", approved=True, approval_id=pending["approvals"][0]["approval_id"],
        model=approval_model,
    ))
    assert resumed["status"] == "ok"
    assert resumed["answer"] == "Pipeline approval completed."

    print(json.dumps({"tools": len(tools), "status": "ok", "approval": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
