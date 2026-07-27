"""No-network smoke checks for the Prokka/Bakta annotation pipeline."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
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
from tools.pipeline_runner.outputs import finalize_output_records


def _load_workflow_module():
    workflow_path = PROJECT_ROOT / "pipelines" / "bacterial_annotation" / "workflow.py"
    spec = spec_from_file_location("bioagent_bacterial_annotation_workflow", workflow_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load workflow module: {workflow_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _output_paths(runtime_config) -> dict[str, Path]:
    return {
        record["name"]: Path(record["path"])
        for record in runtime_config.output_records
    }


def _write_prokka_outputs(command: list[str], genome_path: Path) -> None:
    output_dir = Path(command[command.index("--outdir") + 1])
    prefix = command[command.index("--prefix") + 1]
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


def _write_bakta_outputs(command: list[str], genome_path: Path) -> None:
    output_dir = Path(command[command.index("--output") + 1])
    prefix = command[command.index("--prefix") + 1]
    content_by_extension = {
        "gff3": "##gff-version 3\ncontig_1\tBakta\tCDS\t1\t18\t.\t+\t0\tID=cds1\n",
        "gbff": "LOCUS       contig_1 18 bp DNA\n",
        "faa": ">cds1 hypothetical protein\nMKFGP\n",
        "ffn": ">cds1\nATGAAATTTGGGCCC\n",
        "fna": genome_path.read_text(encoding="utf-8"),
        "tsv": "Sequence Id\tType\tLocus Tag\tProduct\ncontig_1\tcds\tECK12_0001\thypothetical protein\n",
        "txt": "sequences: 2\nsize: 564\ncoding sequences: 1\ntRNAs: 1\n",
        "inference.tsv": "locus\tscore\tevalue\nECK12_0001\t100\t0\n",
        "hypotheticals.tsv": "locus\tlength\nECK12_0001\t5\n",
        "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>\n",
    }
    for extension, content in content_by_extension.items():
        (output_dir / f"{prefix}.{extension}").write_text(content, encoding="utf-8")
    (output_dir / f"{prefix}.json").write_text(
        json.dumps(
            {
                "version": {"bakta": "1.11.3", "db": "6.0", "dbType": "light"},
                "stats": {"size": 564, "sequences": 2, "cds": 1, "trna": 1},
            }
        ),
        encoding="utf-8",
    )
    (output_dir / f"{prefix}.png").write_bytes(b"\x89PNG\r\n\x1a\nmock")


def main() -> int:
    workflow = _load_workflow_module()
    with TemporaryDirectory(prefix="bioagent-bacterial-annotation-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        pipeline_dir = PROJECT_ROOT / "pipelines" / "bacterial_annotation"
        genome_path = pipeline_dir / "data" / "input" / "example_contigs.fasta"
        bakta_db_path = temporary_path / "bakta-db-light"
        bakta_db_path.mkdir()
        commands: list[list[str]] = []

        def fake_run(command, **_kwargs):
            command = [str(value) for value in command]
            commands.append(command)
            executable = Path(command[0]).name.lower()
            if "--version" in command:
                version = "prokka 1.15.6\n" if "prokka" in executable else "bakta 1.11.3\n"
                return subprocess.CompletedProcess(command, 0, stdout=version, stderr="")
            if "prokka" in executable:
                _write_prokka_outputs(command, genome_path)
                stderr = "Prokka progress\n"
            else:
                _write_bakta_outputs(command, genome_path)
                stderr = "Bakta progress\n"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="Annotation complete\n",
                stderr=stderr,
            )

        def fake_which(name: str) -> str:
            return f"/mock/bin/{name}"

        prokka_context = prepare_pipeline_context(
            pipeline_name="bacterial_annotation",
            artifact_dir=temporary_path / "prokka-artifacts",
            run_id="prokka-smoke",
            input_overrides={"genome": str(genome_path)},
            config_overrides={
                "prefix": "ecoli_prokka",
                "genus": "Escherichia",
                "species": "coli",
                "strain": "K-12",
                "cpus": 2,
                "translation_table": 11,
                "locus_tag": "ECK12",
                "compliant": True,
                "rfam": True,
            },
        )
        prokka_runtime = write_runtime_config(prokka_context)
        prokka_values = load_yaml_config(prokka_runtime.path)
        assert len(prokka_runtime.output_records) == 16
        assert prokka_values["params"]["annotator"] == "prokka"
        assert prokka_values["params"]["cpus"] == 2

        with (
            patch.object(workflow.shutil, "which", side_effect=fake_which),
            patch.object(workflow.subprocess, "run", side_effect=fake_run),
        ):
            prokka_metrics = workflow.run(prokka_runtime.path)

        assert prokka_metrics["status"] == "ok"
        assert prokka_metrics["annotator"] == "prokka"
        assert prokka_metrics["tool_version"] == "prokka 1.15.6"
        assert prokka_metrics["input_contigs"] == 2
        assert prokka_metrics["input_bases"] == 564
        assert prokka_metrics["annotation_summary"]["cds"] == 1
        prokka_command = commands[-1]
        assert "--cpus" in prokka_command
        assert "--gcode" in prokka_command
        assert "--locustag" in prokka_command
        assert "--compliant" in prokka_command
        assert "--rfam" in prokka_command

        prokka_paths = _output_paths(prokka_runtime)
        required_prokka_paths = [
            path
            for record in prokka_runtime.output_records
            if record["required"]
            for path in [Path(record["path"])]
        ]
        assert all(path.is_file() for path in required_prokka_paths)
        assert not prokka_paths["bakta_json"].exists()
        assert all(can_serve_artifact(path) for path in required_prokka_paths)
        assert artifact_content_type(prokka_paths["gff"]) == "text/plain; charset=utf-8"
        prokka_files, finalized_prokka_outputs = finalize_output_records(
            prokka_runtime.output_records
        )
        assert len(prokka_files) == 11
        assert sum(not item["exists"] for item in finalized_prokka_outputs) == 5
        with zipfile.ZipFile(prokka_paths["bundle"]) as archive:
            assert "ecoli_prokka.gff" in archive.namelist()
            assert "ecoli_prokka.gbk" in archive.namelist()

        bakta_context = prepare_pipeline_context(
            pipeline_name="bacterial_annotation",
            artifact_dir=temporary_path / "bakta-artifacts",
            run_id="bakta-smoke",
            input_overrides={"genome": str(genome_path)},
            config_overrides={
                "annotator": "bakta",
                "prefix": "ecoli_bakta",
                "genus": "Escherichia",
                "species": "coli",
                "strain": "K-12",
                "cpus": 4,
                "translation_table": 11,
                "locus_tag": "ECK12",
                "compliant": True,
                "bakta_db_path": str(bakta_db_path),
                "gram": "-",
                "meta": True,
                "keep_contig_headers": True,
            },
        )
        bakta_runtime = write_runtime_config(bakta_context)
        with (
            patch.object(workflow.shutil, "which", side_effect=fake_which),
            patch.object(workflow.subprocess, "run", side_effect=fake_run),
        ):
            bakta_metrics = workflow.annotate_bacterial_genome(bakta_runtime.path)

        assert bakta_metrics["annotator"] == "bakta"
        assert bakta_metrics["tool"] == "Bakta"
        assert bakta_metrics["tool_version"] == "bakta 1.11.3"
        assert bakta_metrics["database_path"] == str(bakta_db_path.resolve())
        assert bakta_metrics["database_version"] == "6.0"
        assert bakta_metrics["database_type"] == "light"
        assert bakta_metrics["annotation_summary"]["cds"] == 1
        bakta_command = commands[-1]
        assert "--db" in bakta_command
        assert "--output" in bakta_command
        assert "--threads" in bakta_command
        assert "--translation-table" in bakta_command
        assert "--gram" in bakta_command
        assert "--meta" in bakta_command
        assert "--keep-contig-headers" in bakta_command
        assert "--rfam" not in bakta_command

        bakta_paths = _output_paths(bakta_runtime)
        assert all(path.is_file() for path in bakta_paths.values())
        bakta_files, finalized_bakta_outputs = finalize_output_records(
            bakta_runtime.output_records
        )
        assert len(bakta_files) == 16
        assert all(item["exists"] for item in finalized_bakta_outputs)
        assert "Bakta" in bakta_paths["report"].read_text(encoding="utf-8")
        assert "##gff-version 3" in bakta_paths["gff"].read_text(encoding="utf-8")
        assert bakta_paths["genbank"].read_text(encoding="utf-8").startswith("LOCUS")
        with zipfile.ZipFile(bakta_paths["bundle"]) as archive:
            assert "ecoli_bakta.gff3" in archive.namelist()
            assert "ecoli_bakta.gbff" in archive.namelist()
            assert "ecoli_bakta.json" in archive.namelist()

        try:
            workflow._validate_parameters({"annotator": "unknown"})
        except ValueError as exc:
            assert "annotator" in str(exc)
        else:
            raise AssertionError("Unknown annotator was accepted.")

        try:
            workflow._validate_parameters({"translation_table": 99})
        except ValueError as exc:
            assert "translation_table" in str(exc)
        else:
            raise AssertionError("Unsupported translation table was accepted.")

        try:
            workflow._validate_parameters({"annotator": "prokka", "gram": "-"})
        except ValueError as exc:
            assert "only valid" in str(exc)
        else:
            raise AssertionError("Bakta-only parameters were accepted for Prokka.")

        with patch.dict(workflow.os.environ, {"BAKTA_DB": str(bakta_db_path)}):
            assert workflow._validate_parameters({"annotator": "prokka"})[
                "bakta_db_path"
            ] == ""

        assert workflow._bakta_log_database_details(
            "db: /opt/bakta-db/db, version 6.0, full\n"
        ) == ("6.0", "full")

        with patch.dict(workflow.os.environ, {"BAKTA_DB": ""}):
            try:
                workflow._validate_parameters({"annotator": "bakta"})
            except ValueError as exc:
                assert "requires bakta_db_path" in str(exc)
            else:
                raise AssertionError("Bakta without a database was accepted.")

        try:
            workflow._validate_parameters(
                {"annotator": "bakta", "bakta_db_path": str(temporary_path / "missing-db")}
            )
        except FileNotFoundError as exc:
            assert "database directory" in str(exc)
        else:
            raise AssertionError("A missing Bakta database directory was accepted.")

        try:
            workflow._validate_parameters(
                {
                    "annotator": "bakta",
                    "bakta_db_path": str(bakta_db_path),
                    "meta": True,
                    "complete": True,
                }
            )
        except ValueError as exc:
            assert "cannot both" in str(exc)
        else:
            raise AssertionError("Bakta meta and complete modes were combined.")

        prokka_values["params"]["prefix"] = "bad;prefix"
        write_yaml_config(prokka_values, prokka_runtime.path)
        try:
            workflow.run(prokka_runtime.path)
        except ValueError as exc:
            assert "prefix" in str(exc)
        else:
            raise AssertionError("Unsafe annotation prefix was accepted.")

        prokka_values["params"]["prefix"] = "annotation"
        write_yaml_config(prokka_values, prokka_runtime.path)
        with patch.object(workflow.shutil, "which", return_value=None):
            try:
                workflow.run(prokka_runtime.path)
            except RuntimeError as exc:
                assert "not installed" in str(exc)
            else:
                raise AssertionError("Missing annotator executable was not reported.")

        prokka_values["params"]["prefix"] = "annotation"
        write_yaml_config(prokka_values, prokka_runtime.path)

        def failing_run(command, **_kwargs):
            command = [str(value) for value in command]
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, stdout="prokka 1.15.6\n", stderr="")
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="mock failure")

        with (
            patch.object(workflow.shutil, "which", return_value="/mock/bin/prokka"),
            patch.object(workflow.subprocess, "run", side_effect=failing_run),
        ):
            try:
                workflow.run(prokka_runtime.path)
            except RuntimeError as exc:
                assert "exit code 2" in str(exc)
            else:
                raise AssertionError("Annotator failure was not propagated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
