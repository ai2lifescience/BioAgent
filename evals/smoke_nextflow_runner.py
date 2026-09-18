"""No-Nextflow-install smoke checks for the Nextflow runner contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.runtime_tools.pipelines.generic_nextflow.workflow import run as run_example_step
from tools.runtime_tools.pipeline_runtime.engine.runner import run_pipeline
from tools.runtime_tools.pipeline_runtime.engine.config import load_pipeline_config


def _fake_nextflow_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    params_path = Path(command[command.index("-params-file") + 1])
    config = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    assert Path(config["agent_config_path"]) == params_path
    output_dir = Path(config["nextflow_output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    if "-preview" not in command:
        metrics = {
            "status": "ok",
            "pipeline": "generic_nextflow",
            "sequence_length": 24,
            "min_length": config["params"]["min_length"],
            "passes_min_length": 24 >= config["params"]["min_length"],
        }
        (output_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_dir / "report.md").write_text(
            "# Generic Nextflow Pipeline Report\n",
            encoding="utf-8",
        )
        (output_dir / "normalized.fasta").write_text(
            ">generic_nextflow|segment1\nACGTACGTNNNNACGTTGCAACGT\n",
            encoding="utf-8",
        )
    return subprocess.CompletedProcess(command, 0, stdout="nextflow test double\n", stderr="")


def main() -> int:
    pipeline_dir = PROJECT_ROOT / "tools" / "runtime_tools" / "pipelines" / "generic_nextflow"
    inputs = {
        "sequence": str(pipeline_dir / "data/input/sequences_segment1.fasta"),
        "metadata": str(pipeline_dir / "data/input/metadata.tsv"),
    }

    with TemporaryDirectory(prefix="agent-nextflow-step-") as step_dir:
        previous_dir = Path.cwd()
        try:
            os.chdir(step_dir)
            config, _ = load_pipeline_config(pipeline_dir)
            metrics = run_example_step(
                config,
                pipeline_dir / "data/input/sequences_segment1.fasta",
                pipeline_dir / "data/input/metadata.tsv",
            )
            assert metrics["sequence_length"] == 24
            assert metrics["metadata_rows"] == 1
            assert {path.name for path in Path(step_dir).iterdir()} == {
                "metrics.json",
                "normalized.fasta",
                "report.md",
            }
        finally:
            os.chdir(previous_dir)

    with TemporaryDirectory(prefix="agent-nextflow-runner-") as artifact_dir:
        with patch(
            "tools.runtime_tools.pipeline_runtime.engine.nextflow._nextflow_command",
            return_value=["nextflow-test-double"],
        ), patch(
            "tools.runtime_tools.pipeline_runtime.engine.nextflow.subprocess.run",
            side_effect=_fake_nextflow_run,
        ):
            result = run_pipeline(
                pipeline_name="generic_nextflow",
                artifact_dir=artifact_dir,
                run_id="smoke",
                cores=2,
                input_overrides=inputs,
                config_overrides={"min_length": 25},
            )
            preview = run_pipeline(
                pipeline_name="generic_nextflow",
                artifact_dir=artifact_dir,
                run_id="preview",
                dry_run=True,
                input_overrides=inputs,
            )

        assert result["status"] == "ok"
        assert result["engine"] == "nextflow"
        assert result["cores"] == 2
        assert result["metrics"]["min_length"] == 25
        assert result["metrics"]["passes_min_length"] is False
        assert len(result["files"]) == 3
        assert all(record["exists"] for record in result["output_records"])
        assert result["command"][:3] == [
            "nextflow-test-double",
            "-c",
            str(pipeline_dir / "nextflow.config"),
        ]
        assert "-params-file" in result["command"]
        assert "-work-dir" in result["command"]

        assert preview["status"] == "ok"
        assert preview["dry_run"] is True
        assert "-preview" in preview["command"]
        assert preview["files"] == []
        assert preview["metrics"] == {}
        assert not any(record["exists"] for record in preview["output_records"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
