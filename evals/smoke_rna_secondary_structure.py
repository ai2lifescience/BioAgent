"""No-network smoke checks for the ViennaRNA RNAfold pipeline."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.artifacts import artifact_content_type, can_serve_artifact
from tools.pipeline_config import load_yaml_config
from tools.pipeline_runner.config import write_runtime_config
from tools.pipeline_runner.core import prepare_pipeline_context


def _load_workflow_module():
    workflow_path = PROJECT_ROOT / "pipelines" / "rna_secondary_structure" / "workflow.py"
    spec = spec_from_file_location("bioagent_rna_secondary_structure_workflow", workflow_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load workflow module: {workflow_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    workflow = _load_workflow_module()
    with TemporaryDirectory(prefix="bioagent-rna-secondary-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        pipeline_dir = PROJECT_ROOT / "pipelines" / "rna_secondary_structure"
        rna_path = pipeline_dir / "data" / "input" / "example_rna.fasta"
        context = prepare_pipeline_context(
            pipeline_name="rna_secondary_structure",
            artifact_dir=temporary_path / "artifacts",
            run_id="smoke",
            input_overrides={"rna": str(rna_path)},
            config_overrides={"temperature_c": 30, "max_sequence_length": 100},
        )
        runtime_config = write_runtime_config(context)
        runtime_values = load_yaml_config(runtime_config.path)
        assert len(runtime_config.output_records) == 5
        assert runtime_values["rna_path"] == str(rna_path.resolve())
        assert runtime_values["params"]["temperature_c"] == 30.0

        commands: list[list[str]] = []

        def fake_run(command, **kwargs):
            command = [str(value) for value in command]
            commands.append(command)
            if "--version" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="RNAfold 2.7.0\n",
                    stderr="",
                )
            input_text = str(kwargs.get("input") or "")
            if input_text.startswith(">hairpin_1"):
                stdout = ">hairpin_1\nGGGAAACCC\n(((...))) (-2.40)\n"
            else:
                stdout = ">hairpin_2\nGCGCUUCGCGC\n((((...)))) (-3.10)\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with (
            patch.object(workflow.shutil, "which", return_value="/mock/bin/RNAfold"),
            patch.object(workflow.subprocess, "run", side_effect=fake_run),
        ):
            metrics = workflow.run(runtime_config.path)

        assert metrics["status"] == "ok"
        assert metrics["tool_version"] == "RNAfold 2.7.0"
        assert metrics["sequence_count"] == 2
        assert metrics["total_nt"] == 20
        assert metrics["temperature_c"] == 30.0
        assert metrics["mean_mfe_kcal_mol"] == -2.75
        assert len(commands) == 3
        assert commands[1][1:] == ["--noPS", "--temp", "30.0"]

        output_paths = {
            record["name"]: Path(record["path"])
            for record in runtime_config.output_records
        }
        assert all(path.is_file() for path in output_paths.values())
        assert all(can_serve_artifact(path) for path in output_paths.values())
        assert artifact_content_type(output_paths["dot_bracket"]) == "text/plain; charset=utf-8"
        assert "hairpin_1\t9\t-2.40\t(((...)))" in output_paths["structures"].read_text(
            encoding="utf-8"
        )

        invalid_path = temporary_path / "invalid.fasta"
        invalid_path.write_text(">bad\nACGUZ\n", encoding="utf-8")
        try:
            workflow._read_fasta(invalid_path, 100)
        except ValueError as exc:
            assert "unsupported nucleotide" in str(exc)
        else:
            raise AssertionError("Invalid RNA symbols were accepted.")

        with patch.object(workflow.shutil, "which", return_value=None):
            try:
                workflow.run(runtime_config.path)
            except RuntimeError as exc:
                assert "not installed" in str(exc)
            else:
                raise AssertionError("Missing RNAfold executable was not reported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
