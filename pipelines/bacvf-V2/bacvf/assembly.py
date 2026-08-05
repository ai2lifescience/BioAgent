"""Trimmomatic and metagenome assembly orchestration."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .command import CommandRunner
from .config import PipelineConfig
from .errors import ExternalToolError
from .input import InputSet, open_sequence_text


@dataclass(frozen=True)
class AssemblyResult:
    """Assembly path and preprocessing provenance."""

    path: Path
    source: str
    trimmed_reads: tuple[Path, ...]
    unpaired_reads: tuple[Path, ...]



@dataclass(frozen=True)
class ReadPreparation:
    """Trimmed reads and discarded mate outputs."""

    trimmed_reads: tuple[Path, ...]
    unpaired_reads: tuple[Path, ...]

def trimmomatic_command(
    reads: Sequence[Path], output_dir: Path, config: PipelineConfig
) -> tuple[list[str], tuple[Path, ...], tuple[Path, ...]]:
    """Build single- or paired-end Trimmomatic arguments."""
    tool = config.value("tools", "trimmomatic")
    executable = str(tool["executable"])
    options = [str(item) for item in tool.get("options", [])]
    if len(reads) == 1:
        trimmed = output_dir / "trimmed.fastq.gz"
        command = [
            executable, *[str(item) for item in tool.get("prefix_options", [])],
            "SE", "-threads", str(config.threads), str(reads[0]), str(trimmed), *options,
        ]
        return command, (trimmed,), ()
    if len(reads) == 2:
        paired1 = output_dir / "trimmed_R1.fastq.gz"
        unpaired1 = output_dir / "unpaired_R1.fastq.gz"
        paired2 = output_dir / "trimmed_R2.fastq.gz"
        unpaired2 = output_dir / "unpaired_R2.fastq.gz"
        command = [
            executable, *[str(item) for item in tool.get("prefix_options", [])],
            "PE", "-threads", str(config.threads), str(reads[0]), str(reads[1]),
            str(paired1), str(unpaired1), str(paired2), str(unpaired2), *options,
        ]
        return command, (paired1, paired2), (unpaired1, unpaired2)
    raise ValueError("Trimmomatic requires one read or an explicit R1/R2 pair.")



def prepare_reads(
    inputs: InputSet,
    work_dir: Path,
    config: PipelineConfig,
    runner: CommandRunner,
) -> ReadPreparation:
    """Quality-trim FASTQ reads without assembling them."""
    if inputs.kind != "fastq":
        raise ValueError("Direct reads analysis requires FASTQ input.")
    trim_dir = work_dir / "trimmed"
    trim_dir.mkdir(parents=True, exist_ok=True)
    command, trimmed, unpaired = trimmomatic_command(inputs.files, trim_dir, config)
    runner.run(
        command,
        tool="Trimmomatic",
        log_path=work_dir.parent / "logs" / "trimmomatic.log",
    )
    if not runner.dry_run:
        for path in trimmed:
            if not path.is_file() or path.stat().st_size == 0:
                raise ExternalToolError(
                    f"Trimmomatic completed without a non-empty output: {path}"
                )
    return ReadPreparation(tuple(trimmed), tuple(unpaired))

def assembler_command(
    trimmed: Sequence[Path],
    unpaired: Sequence[Path],
    output_dir: Path,
    config: PipelineConfig,
) -> list[str]:
    """Build a metaSPAdes command without isolate-mode assumptions."""
    tool = config.value("tools", "assembler")
    options = [str(item) for item in tool.get("options", [])]
    if any(item.lstrip("-").lower() == "isolate" for item in options):
        raise ValueError("Assembler options must not enable isolate mode.")
    command = [
        str(tool["executable"]), *[str(item) for item in tool.get("prefix_options", [])],
        *options, "-t", str(config.threads),
    ]
    memory = tool.get("memory_gb")
    if memory not in (None, ""):
        command.extend(["-m", str(memory)])
    command.extend(["-o", str(output_dir)])
    if len(trimmed) == 2:
        command.extend(["-1", str(trimmed[0]), "-2", str(trimmed[1])])
        if tool.get("include_unpaired", False):
            for index, path in enumerate(unpaired, start=1):
                command.extend([f"--s{index}", str(path)])
    else:
        command.extend(["-s", str(trimmed[0])])
    return command


def _copy_plain_fasta(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=target.parent
    ) as temporary:
        temporary_path = Path(temporary.name)
        with open_sequence_text(source) as handle:
            shutil.copyfileobj(handle, temporary)
    temporary_path.replace(target)


def prepare_assembly(
    inputs: InputSet,
    work_dir: Path,
    config: PipelineConfig,
    runner: CommandRunner,
) -> AssemblyResult:
    """Use supplied contigs or build a metagenome assembly from reads."""
    assembly_dir = work_dir / "assembly"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    if inputs.kind == "fasta":
        assembly = assembly_dir / "assembly.fasta"
        _copy_plain_fasta(inputs.files[0], assembly)
        return AssemblyResult(assembly, "supplied", (), ())
    trim_dir = work_dir / "trimmed"
    trim_dir.mkdir(parents=True, exist_ok=True)
    trim_command, trimmed, unpaired = trimmomatic_command(inputs.files, trim_dir, config)
    runner.run(
        trim_command, tool="Trimmomatic", log_path=work_dir.parent / "logs" / "trimmomatic.log"
    )
    spades_dir = assembly_dir / "metaspades"
    command = assembler_command(trimmed, unpaired, spades_dir, config)
    runner.run(
        command, tool="metaSPAdes", log_path=work_dir.parent / "logs" / "metaspades.log"
    )
    assembly = spades_dir / "contigs.fasta"
    if not runner.dry_run and (not assembly.is_file() or assembly.stat().st_size == 0):
        raise ExternalToolError(
            f"metaSPAdes completed without a non-empty contigs.fasta: {assembly}"
        )
    return AssemblyResult(assembly, "metaspades", tuple(trimmed), tuple(unpaired))
