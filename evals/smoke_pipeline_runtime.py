"""Offline end-to-end check for the local ShellTool pipeline protocol."""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.infrastructure.pipeline_runtime import service
from tools.infrastructure.pipeline_runtime.commands import dispatch, parse_command


def main() -> int:
    with TemporaryDirectory(prefix="agent-local-pipeline-") as temporary:
        root = Path(temporary)
        staged = dispatch(root, "agent-pipeline example --pipeline template_shell")
        inputs = {"reads" if item["workspace_path"].endswith(".txt") else "metadata": item["workspace_path"] for item in staged["files"]}
        plan = service.plan(root, "template_shell", inputs, {})
        assert plan["status"] == "planned"
        parsed = parse_command(plan["command"])
        assert parsed.operation == "run" and parsed.plan_id == plan["plan_id"]
        first = dispatch(root, plan["command"])
        second = service.start(root, plan["plan_id"])
        assert first["job_id"] == second["job_id"]
        completed = dispatch(root, f"agent-pipeline wait --job-id {first['job_id']} --seconds 15")
        assert completed["status"] == "succeeded", completed
        result = dispatch(root, f"agent-pipeline results --job-id {first['job_id']}")
        assert result["metrics"]["sequence_count"] == 3
        assert result["metrics"]["assigned_subtype_count"] == 3
        assert len(result["tables"][0]["rows"]) == 3
        assert result["bundle_path"].endswith("results.zip")
    print("local pipeline protocol: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
