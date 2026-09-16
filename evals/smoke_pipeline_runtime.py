"""Offline end-to-end check for the local ShellTool pipeline protocol."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.runtime_tools.pipeline_runtime import service


def main() -> int:
    with TemporaryDirectory(prefix="bioagent-local-pipeline-") as temporary:
        root = Path(temporary)
        staged = service.stage_example(root, "example_sequence_qc")
        inputs = {"reads" if item["workspace_path"].endswith(".fastq") else "metadata": item["workspace_path"] for item in staged["files"]}
        plan = service.plan(root, "example_sequence_qc", inputs, {})
        assert plan["status"] == "planned"
        first = service.start(root, plan["plan_id"])
        second = service.start(root, plan["plan_id"])
        assert first["job_id"] == second["job_id"]
        completed = service.wait(root, first["job_id"], 15)
        assert completed["status"] == "succeeded", completed
        result = service.results(root, first["job_id"])
        assert result["metrics"]["input_read_count"] == 4
        assert result["metrics"]["passed_read_count"] == 2
        assert len(result["tables"][0]["rows"]) == 4
        assert result["bundle_path"].endswith("results.zip")
    print("local pipeline protocol: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
