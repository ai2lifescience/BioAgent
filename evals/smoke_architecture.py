"""Offline smoke checks for the Agents SDK BioAgent architecture."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from harness import runtime
from harness.agent import create_agent
from harness.guardrails import input_check
from harness.tools import build_tools


def main() -> int:
    tools = build_tools()
    names = {tool.name for tool in tools}
    expected = {"sequence_analysis", "database_lookup", "pdb_download", "file_inspection", "pipeline_runner", "species_report"}
    assert expected <= names
    assert create_agent("gpt-oss", model=ScriptedModel()).name == "BioAgent"

    runtime.SESSION_DB = PROJECT_ROOT / "runtime" / "smoke_agents.sqlite3"
    model = ScriptedModel([
        ModelStep(output=[function_call("sequence_analysis", {"sequence": "ACGT"}, call_id="call-1")]),
        ModelStep(output=[assistant_message("The sequence has 50% GC content.")]),
    ])
    result = asyncio.run(runtime.async_run_bioagent("Analyze ACGT", session_id="smoke_agents", model=model))
    assert result["runtime"] == "agents_sdk"
    assert result["answer"] == "The sequence has 50% GC content."
    assert result["evidence"]["tools"] == ["sequence_analyze"]
    assert any(event["event"] == "sdk_trace_started" for event in result["trace"])
    assert any(event["event"] == "guardrail_completed" for event in result["trace"])

    print(json.dumps({"tools": len(tools), "status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
