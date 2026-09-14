"""Offline smoke check for pipeline tools through the SDK harness."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from harness import runtime


def main() -> int:
    pipeline_dir = PROJECT_ROOT / "pipelines" / "generic_bio" / "data" / "input"
    model = ScriptedModel([
        ModelStep(output=[function_call("pipeline_runner", {
            "pipeline_name": "generic_bio",
            "input_overrides": {
                "reads": str(pipeline_dir / "example_reads.fastq"),
                "reference": str(pipeline_dir / "example_reference.fasta"),
                "metadata": str(pipeline_dir / "example_samples.tsv"),
            },
        }, call_id="pipeline-1")]),
        ModelStep(output=[assistant_message("Pipeline completed; inspect the generated artifacts for metrics and reports.")]),
    ])
    runtime.SESSION_DB = PROJECT_ROOT / "runtime" / "smoke_pipeline_agents.sqlite3"
    result = asyncio.run(runtime.async_run_bioagent("Run the generic bio pipeline", session_id="smoke_pipeline_agents", model=model))
    assert result["verification"]["status"] in {"ok", "warning"}
    assert result["evidence"]["tools"] == ["pipeline_runner"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
