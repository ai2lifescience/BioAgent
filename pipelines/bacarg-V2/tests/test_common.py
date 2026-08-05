from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from bacarg.assembly import assembler_command, trimmomatic_command
from bacarg.batch import run_samples
from bacarg.command import CommandRunner
from bacarg.config import ConfigurationError, load_config
from bacarg.input import (
    InputValidationError,
    detect_sequence_format,
    discover_samples,
    validate_inputs,
)
from bacarg.pipeline import run_pipeline
from bacarg.prokka import prokka_command
from bacarg.qc import assembly_qc


ROOT = Path(__file__).resolve().parents[1]


def fasta(path: Path, name: str = "contig1", sequence: str = "ACGTACGT") -> Path:
    path.write_text(f">{name}\n{sequence}\n", encoding="utf-8")
    return path


def fastq(path: Path, name: str = "read1") -> Path:
    path.write_text(f"@{name}\nACGT\n+\nIIII\n", encoding="utf-8")
    return path


def config_file(tmp_path: Path) -> Path:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["pipeline"]["threads"] = 2
    data["databases"] = {
        "abricate_datadir": "db",
        "metadata": "metadata.tsv",
        "manifest": None,
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_fasta_and_fastq_content_detection(tmp_path: Path) -> None:
    assert detect_sequence_format(fasta(tmp_path / "wrong.fastq")) == "fasta"
    assert detect_sequence_format(fastq(tmp_path / "wrong.fasta")) == "fastq"


@pytest.mark.parametrize("kind", ["fasta", "fastq"])
def test_gzip_magic_detection(tmp_path: Path, kind: str) -> None:
    path = tmp_path / f"{kind}.data"
    content = ">c\nACGT\n" if kind == "fasta" else "@r\nACGT\n+\nIIII\n"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(content)
    assert detect_sequence_format(path) == kind


@pytest.mark.parametrize(
    "content",
    ["", "@r\nACGT\n+\n", ">c\n@r\nACGT\n+\nIIII\n"],
)
def test_empty_incomplete_and_mixed_content_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "bad.txt"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(InputValidationError):
        detect_sequence_format(path)


def test_count_and_type_rules(tmp_path: Path) -> None:
    a = fasta(tmp_path / "a.fa")
    b = fasta(tmp_path / "b.fa")
    r1 = fastq(tmp_path / "r1.fq")
    r2 = fastq(tmp_path / "r2.fq")
    output = tmp_path / "result"
    with pytest.raises(InputValidationError, match="exactly one"):
        validate_inputs([a, b], output)
    with pytest.raises(InputValidationError, match="Mixed"):
        validate_inputs([a, r1], output)
    with pytest.raises(InputValidationError, match="At most two"):
        validate_inputs([r1, r2, a], output)
    with pytest.raises(InputValidationError, match="Duplicate"):
        validate_inputs([r1, r1], output)
    assert validate_inputs([r1, r2], output).paired is True


def test_sample_id_and_space_paths(tmp_path: Path) -> None:
    directory = tmp_path / "space directory"
    directory.mkdir()
    r1 = fastq(directory / "unsafe sample_R1.fastq")
    r2 = fastq(directory / "unsafe sample_R2.fastq")
    detected = validate_inputs([r1, r2], tmp_path / "out")
    assert detected.sample_id == "unsafe_sample"
    assert validate_inputs([r1], tmp_path / "out2", "../../A B").sample_id == "A_B"


def test_output_cannot_contain_input(tmp_path: Path) -> None:
    path = fasta(tmp_path / "input.fa")
    with pytest.raises(InputValidationError, match="overwrite"):
        validate_inputs([path], tmp_path)


def test_environment_expansion_and_relative_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["databases"]["abricate_datadir"] = "${ARG_DB_ROOT}"
    data["databases"]["metadata"] = "relative/metadata.tsv"
    path = tmp_path / "deployment.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setenv("ARG_DB_ROOT", str(tmp_path / "external db"))
    config = load_config(path)
    assert config.database_path("abricate_datadir") == (tmp_path / "external db").resolve()
    assert config.database_path("metadata") == (tmp_path / "relative/metadata.tsv").resolve()


def test_unset_environment_variable_is_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOT_SET_FOR_TEST", raising=False)
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    data["databases"]["metadata"] = "${NOT_SET_FOR_TEST}"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="NOT_SET_FOR_TEST"):
        load_config(path)


def test_command_runner_dry_run_and_argument_boundaries(tmp_path: Path) -> None:
    log = tmp_path / "tool.log"
    dry = CommandRunner(dry_run=True)
    dry.run(["not installed", "a b"], tool="fake", log_path=log)
    assert dry.commands == [["not installed", "a b"]]
    script = tmp_path / "capture.py"
    capture = tmp_path / "args.json"
    script.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    runner = CommandRunner()
    runner.run(
        [sys.executable, script, capture, "path with spaces", "$literal"],
        tool="capture",
        log_path=tmp_path / "capture.log",
    )
    assert json.loads(capture.read_text(encoding="utf-8")) == [
        "path with spaces",
        "$literal",
    ]


def test_metagenome_command_contracts(tmp_path: Path) -> None:
    config = load_config(config_file(tmp_path))
    reads = [tmp_path / "r1.fastq", tmp_path / "r2.fastq"]
    trim, paired, unpaired = trimmomatic_command(reads, tmp_path / "trim", config)
    assembly = assembler_command(paired, unpaired, tmp_path / "asm", config)
    prokka = prokka_command(tmp_path / "contigs.fa", tmp_path / "prokka", "s", config)
    assert "PE" in trim
    assert "isolate" not in " ".join(assembly).lower()
    assert "--metagenome" in prokka


def test_n50_and_gc(tmp_path: Path) -> None:
    path = tmp_path / "assembly.fa"
    path.write_text(">a\nGGGGGG\n>b\nAATT\n>c\nAA\n", encoding="utf-8")
    metrics = assembly_qc(path)
    assert metrics["n50"] == 6
    assert metrics["contig_count"] == 3
    assert metrics["gc_percent"] == 50.0


def test_dry_run_writes_contract_and_command_plan(tmp_path: Path) -> None:
    sequence = fasta(tmp_path / "mini contigs.fa")
    output = tmp_path / "dry result"
    status = run_pipeline(
        [sequence], output, config_path=config_file(tmp_path), dry_run=True
    )
    assert status["status"] == "success"
    assert status["dry_run"] is True
    assert (output / "arg_hits.tsv").read_text(encoding="utf-8").startswith("sample_id\t")
    assert (output / "arg_hits.jsonl").read_text(encoding="utf-8") == ""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["commands"]) == 2
    assert (output / "raw").is_dir()
    assert (output / "logs").is_dir()
    assert (output / "work").is_dir()


def test_pipeline_failure_writes_failed_status(tmp_path: Path) -> None:
    sequence = fasta(tmp_path / "mini.fa")
    output = tmp_path / "failed"
    with pytest.raises(Exception):
        run_pipeline([sequence], output, config_path=config_file(tmp_path))
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error_type"]


def test_explicit_input_contract_and_genome_variants(tmp_path: Path) -> None:
    read = fastq(tmp_path / "single.fastq")
    reads = validate_inputs([read], tmp_path / "reads-out")
    assert reads.input_type == "reads"
    assert reads.analysis_mode == "assemble"
    for name in ("complete_genome.fasta", "partial_genome.fna", "contigs.fa"):
        sequence = fasta(tmp_path / name)
        genome = validate_inputs(
            [sequence],
            tmp_path / (name + "-out"),
            input_type="genome",
            analysis_mode="genome",
        )
        assert genome.input_type == "genome"
        assert genome.analysis_mode == "genome"
    with pytest.raises(InputValidationError, match="does not match"):
        validate_inputs([read], tmp_path / "bad-type", input_type="genome")
    direct = validate_inputs([read], tmp_path / "direct", analysis_mode="reads")
    assert direct.analysis_mode == "reads"


def test_strict_pairing_directory_and_multi_sample_isolation(tmp_path: Path) -> None:
    r1 = fastq(tmp_path / "batch_A_R1.fastq")
    r2 = fastq(tmp_path / "batch_A_R2.fastq")
    single = fastq(tmp_path / "batch_B.fastq")
    genome = fasta(tmp_path / "batch_C.fasta")
    samples = discover_samples([r2, single, genome, r1], tmp_path / "batch-out")
    assert {sample.sample_id for sample in samples} == {"batch_A", "batch_B", "batch_C"}
    assert sorted(len(sample.files) for sample in samples) == [1, 1, 2]
    flattened = [path for sample in samples for path in sample.files]
    assert len(flattened) == len(set(flattened)) == 4
    left = fastq(tmp_path / "left.fastq")
    right = fastq(tmp_path / "right.fastq")
    with pytest.raises(InputValidationError, match="recognizable R1/R2"):
        validate_inputs([left, right], tmp_path / "bad-pair")
    with pytest.raises(InputValidationError, match="ordered R1/R2"):
        validate_inputs([r2, r1], tmp_path / "reversed")
    single_r1 = fastq(tmp_path / "single_end_R1.fastq")
    discovered_single = discover_samples([single_r1], tmp_path / "single-r1-out")
    assert len(discovered_single) == 1 and discovered_single[0].paired is False
    orphan_dir = tmp_path / "orphans"
    orphan_dir.mkdir()
    fastq(orphan_dir / "orphan_R2.fastq")
    with pytest.raises(InputValidationError, match="R2 without R1"):
        discover_samples([], tmp_path / "orphan-out", input_directory=orphan_dir)


def test_mode_routing_dry_run_and_metadata_contract(tmp_path: Path) -> None:
    config = config_file(tmp_path)
    genome_output = tmp_path / "genome-dry"
    run_pipeline(
        [fasta(tmp_path / "genome.fasta")],
        genome_output,
        config_path=config,
        dry_run=True,
        input_type="genome",
        analysis_mode="genome",
    )
    genome_manifest = json.loads((genome_output / "manifest.json").read_text(encoding="utf-8"))
    assert genome_manifest["analysis_mode"] == "genome"
    assert len(genome_manifest["commands"]) == 2
    assert not any("trimmomatic" in command[0].lower() for command in genome_manifest["commands"])
    assert not any("metaspades" in command[0].lower() for command in genome_manifest["commands"])

    r1 = fastq(tmp_path / "sample_R1.fastq")
    r2 = fastq(tmp_path / "sample_R2.fastq")
    assemble_output = tmp_path / "assemble-dry"
    status = run_pipeline(
        [r1, r2],
        assemble_output,
        config_path=config,
        dry_run=True,
        input_type="reads",
        analysis_mode="assemble",
    )
    manifest = json.loads((assemble_output / "manifest.json").read_text(encoding="utf-8"))
    qc = json.loads((assemble_output / "qc.json").read_text(encoding="utf-8"))
    assert status["input_type"] == "reads"
    assert status["analysis_mode"] == "assemble"
    assert manifest["analysis_mode"] == "assemble"
    assert qc["analysis_mode"] == "assemble"
    assert len(manifest["commands"]) == 4
    assert any("trimmomatic" in command[0].lower() for command in manifest["commands"])
    assert any("metaspades" in command[0].lower() for command in manifest["commands"])

    reads_output = tmp_path / "direct-reads"
    reads_status = run_pipeline(
        [r1, r2],
        reads_output,
        config_path=config,
        dry_run=True,
        input_type="reads",
        analysis_mode="reads",
    )
    reads_manifest = json.loads((reads_output / "manifest.json").read_text(encoding="utf-8"))
    assert reads_status["analysis_mode"] == "reads"
    assert len(reads_manifest["commands"]) == 2
    commands = " ".join(part for command in reads_manifest["commands"] for part in command).lower()
    assert "metaspades" not in commands
    assert "prokka" not in commands

def test_batch_execution_keeps_sample_outputs_separate(tmp_path: Path) -> None:
    first = fasta(tmp_path / "first.fasta")
    second = fasta(tmp_path / "second.fasta")
    output = tmp_path / "batch-results"
    samples = discover_samples([second, first], output)
    statuses = run_samples(
        samples,
        output,
        config_path=config_file(tmp_path),
        dry_run=True,
        threads=1,
    )
    assert {status["sample_id"] for status in statuses} == {"first", "second"}
    for sample in samples:
        sample_output = output / sample.sample_id
        manifest = json.loads((sample_output / "manifest.json").read_text(encoding="utf-8"))
        assert [item["name"] for item in manifest["inputs"]] == [sample.files[0].name]
        assert manifest["analysis_mode"] == "genome"

def test_direct_reads_directory_batch_supports_single_and_paired(tmp_path: Path) -> None:
    input_dir = tmp_path / "reads-input"
    input_dir.mkdir()
    fastq(input_dir / "pair_A_R1.fastq")
    fastq(input_dir / "pair_A_R2.fastq")
    fastq(input_dir / "single_B.fastq")
    output = tmp_path / "reads-batch"
    samples = discover_samples(
        [], output, input_directory=input_dir,
        input_type="reads", analysis_mode="reads",
    )
    assert sorted((item.sample_id, item.paired) for item in samples) == [
        ("pair_A", True), ("single_B", False),
    ]
    statuses = run_samples(
        samples, output, config_path=config_file(tmp_path), dry_run=True, threads=1
    )
    assert len(statuses) == 2
    for sample in samples:
        manifest = json.loads((output / sample.sample_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["analysis_mode"] == "reads"
        assert len(manifest["commands"]) == 2
