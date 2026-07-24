"""No-network smoke checks for the Prokka bacterial annotation pipeline."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.artifacts import artifact_content_type, can_serve_artifact
from tools.pipeline_config import load_yaml_config, write_yaml_config
from tools.pipeline_runner.config import write_runtime_config
from tools.pipeline_runner.core import prepare_pipeline_context


def _load_workflow_module():
    workflow_path = PROJECT_ROOT / "pipelines" / "bacterial_annotation" / "workflow.py"
    spec = spec_from_file_location("bioagent_bacterial_annotation_workflow", workflow_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load workflow module: {workflow_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    workflow = _load_workflow_module()
    with TemporaryDirectory(prefix="bioagent-bacterial-annotation-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        pipeline_dir = PROJECT_ROOT / "pipelines" / "bacterial_annotation"
        genome_path = pipeline_dir / "data" / "input" / "example_contigs.fasta"

        context = prepare_pipeline_context(
            pipeline_name="bacterial_annotation",
            artifact_dir=temporary_path / "artifacts",
            run_id="smoke",
            input_overrides={"genome": str(genome_path)},
            config_overrides={
                "prefix": "ecoli_k12",
                "genus": "Escherichia",
                "species": "coli",
                "strain": "K-12",
                "cpus": 2,
            },
        )
        runtime_config = write_runtime_config(context)
        runtime_values = load_yaml_config(runtime_config.path)
        assert len(runtime_config.output_records) == 11
        assert runtime_values["genome_path"] == str(genome_path.resolve())
        assert runtime_values["params"]["cpus"] == 2

        commands: list[list[str]] = []

        def fake_run(command, **_kwargs):
            command = [str(value) for value in command]
            commands.append(command)
            if "--version" in command:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="prokka 1.15.6\n",
                    stderr="",
                )

            output_dir = Path(command[command.index("--outdir") + 1])
            prefix = command[command.index("--prefix") + 1]
            output_dir.mkdir(parents=True, exist_ok=True)
            content_by_extension = {
                "gff": "##gff-version 3\ncontig_1\tProkka\tCDS\t1\t18\t.\t+\t0\tID=cds1\n",
                "gbk": "LOCUS       contig_1 18 bp DNA\n",
                "faa": ">cds1\nMKFGP\n",
                "ffn": ">cds1\nATGAAATTTGGGCCC\n",
                "fna": genome_path.read_text(encoding="utf-8"),
                "tsv": "locus_tag\tftype\tlen_bp\tproduct\ncds1\tCDS\t15\tprotein\n",
                "txt": "contigs: 2\nbases: 564\nCDS: 1\ntRNA: 1\n",
                "log": "fake Prokka log\n",
            }
            for extension, content in content_by_extension.items():
                (output_dir / f"{prefix}.{extension}").write_text(content, encoding="utf-8")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="Annotation complete\n",
                stderr="Prokka progress\n",
            )

        with (
            patch.object(workflow.shutil, "which", return_value="/mock/bin/prokka"),
            patch.object(workflow.subprocess, "run", side_effect=fake_run),
        ):
            metrics = workflow.run(runtime_config.path)

        assert metrics["status"] == "ok"
        assert metrics["tool_version"] == "prokka 1.15.6"
        assert metrics["input_contigs"] == 2
        assert metrics["input_bases"] == 564
        assert metrics["annotation_summary"]["cds"] == 1
        assert metrics["taxonomy"] == {
            "genus": "Escherichia",
            "species": "coli",
            "strain": "K-12",
        }
        assert len(commands) == 2
        annotation_command = commands[-1]
        assert "--genus" in annotation_command
        assert "--species" in annotation_command
        assert "--strain" in annotation_command
        assert "--force" in annotation_command

        output_paths = {
            record["name"]: Path(record["path"])
            for record in runtime_config.output_records
        }
        assert all(path.is_file() for path in output_paths.values())
        assert all(can_serve_artifact(path) for path in output_paths.values())
        assert artifact_content_type(output_paths["gff"]) == "text/plain; charset=utf-8"
        assert artifact_content_type(output_paths["genbank"]) == "text/plain; charset=utf-8"
        assert artifact_content_type(output_paths["genes"]) == "text/plain; charset=utf-8"
        assert "Bacterial Genome Annotation Report" in output_paths["report"].read_text(
            encoding="utf-8"
        )
        with zipfile.ZipFile(output_paths["bundle"]) as archive:
            assert "ecoli_k12.gff" in archive.namelist()
            assert "ecoli_k12.gbk" in archive.namelist()

        runtime_values["params"]["prefix"] = "bad;prefix"
        write_yaml_config(runtime_values, runtime_config.path)
        try:
            workflow.run(runtime_config.path)
        except ValueError as exc:
            assert "prefix" in str(exc)
        else:
            raise AssertionError("Unsafe Prokka prefix was accepted.")

        runtime_values["params"]["prefix"] = "annotation"
        write_yaml_config(runtime_values, runtime_config.path)
        with patch.object(workflow.shutil, "which", return_value=None):
            try:
                workflow.run(runtime_config.path)
            except RuntimeError as exc:
                assert "not installed" in str(exc)
            else:
                raise AssertionError("Missing Prokka executable was not reported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
