"""Content-based sequence detection, sample grouping, and input safety checks."""

from __future__ import annotations

import gzip
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal, Sequence, TextIO

from .errors import InputValidationError


SUPPORTED_SUFFIXES = (
    ".fa", ".fna", ".fasta", ".fas", ".fq", ".fastq",
    ".fa.gz", ".fna.gz", ".fasta.gz", ".fas.gz", ".fq.gz", ".fastq.gz",
)
_SAFE_SAMPLE = re.compile(r"[^A-Za-z0-9._-]+")
_MATE_PATTERN = re.compile(
    r"^(?P<sample>.*?)(?:(?:[._-]R?)(?P<separated>[12])|R(?P<compact>[12]))"
    r"(?:[._-]?001)?$",
    re.IGNORECASE,
)
InputType = Literal["reads", "genome"]
AnalysisMode = Literal["reads", "genome", "assemble"]


@dataclass(frozen=True)
class InputSet:
    """Validated sequence inputs."""

    files: tuple[Path, ...]
    kind: str
    paired: bool
    compressed: tuple[bool, ...]
    sample_id: str
    input_type: InputType
    analysis_mode: AnalysisMode


def is_gzip(path: Path) -> bool:
    """Detect gzip by magic bytes rather than filename."""
    with path.open("rb") as handle:
        return handle.read(2) == b"\x1f\x8b"


def open_sequence_text(path: Path) -> TextIO:
    """Open plain or gzip-compressed sequence text as UTF-8."""
    raw = path.open("rb")
    try:
        if raw.read(2) == b"\x1f\x8b":
            raw.seek(0)
            binary = gzip.GzipFile(fileobj=raw)
            return io.TextIOWrapper(binary, encoding="utf-8", newline=None)
        raw.seek(0)
        return io.TextIOWrapper(raw, encoding="utf-8", newline=None)
    except Exception:
        raw.close()
        raise


def _nonblank(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        value = line.rstrip("\r\n")
        if value.strip():
            yield value


def _validate_fasta(first: str, lines: Iterator[str], path: Path) -> None:
    records = 0
    has_sequence = False
    for line in (item for item in (first, *()) if item):
        if not line.startswith(">") or not line[1:].strip():
            raise InputValidationError(f"Invalid FASTA header in {path}")
        records += 1
    for line in lines:
        value = line.rstrip("\r\n")
        if not value.strip():
            continue
        if value.startswith(">"):
            if not has_sequence:
                raise InputValidationError(f"FASTA record has no sequence in {path}")
            if not value[1:].strip():
                raise InputValidationError(f"Invalid FASTA header in {path}")
            records += 1
            has_sequence = False
        else:
            if value.startswith("@") or re.search(r"\s", value):
                raise InputValidationError(f"Invalid or mixed FASTA content in {path}")
            has_sequence = True
    if records == 0 or not has_sequence:
        raise InputValidationError(f"FASTA contains no sequence records: {path}")


def _validate_fastq(first: str, lines: Iterator[str], path: Path) -> None:
    if not first.startswith("@") or not first[1:].strip():
        raise InputValidationError(f"Invalid FASTQ header in {path}")
    pending: list[str] = [first]
    record_count = 0
    for line in lines:
        pending.append(line.rstrip("\r\n"))
        if len(pending) == 4:
            header, sequence, plus, quality = pending
            if not header.startswith("@") or not header[1:].strip():
                raise InputValidationError(f"Invalid FASTQ header in {path}")
            if not sequence or re.search(r"\s", sequence):
                raise InputValidationError(f"Invalid FASTQ sequence in {path}")
            if not plus.startswith("+"):
                raise InputValidationError(f"Invalid FASTQ separator in {path}")
            if len(sequence) != len(quality):
                raise InputValidationError(f"FASTQ sequence/quality length mismatch in {path}")
            record_count += 1
            pending = []
    if pending:
        raise InputValidationError(f"Incomplete FASTQ record in {path}")
    if record_count == 0:
        raise InputValidationError(f"FASTQ contains no records: {path}")


def detect_sequence_format(path: Path) -> str:
    """Return ``fasta`` or ``fastq`` after validating file content."""
    path = Path(path)
    if not path.exists():
        raise InputValidationError(f"Input file does not exist: {path}")
    if not path.is_file():
        raise InputValidationError(f"Input path is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise InputValidationError(f"Input file is not readable: {path}")
    try:
        with open_sequence_text(path) as handle:
            iterator = iter(handle)
            first = next(_nonblank(iterator), None)
            if first is None:
                raise InputValidationError(f"Input file is empty: {path}")
            if first.startswith(">"):
                _validate_fasta(first, iterator, path)
                return "fasta"
            if first.startswith("@"):
                _validate_fastq(first, iterator, path)
                return "fastq"
    except (gzip.BadGzipFile, UnicodeError, OSError) as exc:
        raise InputValidationError(f"Cannot read sequence content from {path}: {exc}") from exc
    raise InputValidationError(f"Input is neither valid FASTA nor FASTQ: {path}")


def sanitize_sample_id(value: str) -> str:
    """Return a filesystem-safe, stable sample identifier."""
    cleaned = _SAFE_SAMPLE.sub("_", value.strip()).strip("._-")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "sample"
    return cleaned[:100]


def _derived_sample(files: Sequence[Path]) -> str:
    names = []
    for path in files:
        name = path.name
        if name.lower().endswith(".gz"):
            name = name[:-3]
        name = re.sub(r"\.(?:fa|fna|fasta|fas|fq|fastq)$", "", name, flags=re.I)
        name = re.sub(r"([._-])R?[12]$", "", name, flags=re.I)
        names.append(name)
    if len(names) == 2:
        first = _mate_key(files[0])
        second = _mate_key(files[1])
        if first is not None and second is not None and first[0].casefold() == second[0].casefold():
            return sanitize_sample_id(first[0] or "sample")
        common = os.path.commonprefix(names).rstrip("._-")
        return sanitize_sample_id(common or names[0])
    return sanitize_sample_id(names[0])


def _sequence_stem(path: Path) -> str:
    name = path.name
    if name.lower().endswith(".gz"):
        name = name[:-3]
    return re.sub(r"\.(?:fa|fna|fasta|fas|fq|fastq)$", "", name, flags=re.I)


def _mate_key(path: Path) -> tuple[str, int] | None:
    match = _MATE_PATTERN.fullmatch(_sequence_stem(path))
    if match is None:
        return None
    mate = match.group("separated") or match.group("compact")
    sample = match.group("sample").rstrip("._-")
    return sample, int(mate)


def _validate_pair(files: Sequence[Path]) -> None:
    if len(files) != 2:
        return
    first = _mate_key(files[0])
    second = _mate_key(files[1])
    if first is None or second is None:
        raise InputValidationError(
            "Two FASTQ files require recognizable R1/R2 (or _1/_2) mate names; "
            "use separate runs for unrelated single-end samples."
        )
    if (
        first[0].casefold() != second[0].casefold()
        or first[1] != 1
        or second[1] != 2
    ):
        raise InputValidationError(
            "FASTQ pair must be an ordered R1/R2 pair with the same sample stem."
        )


def _resolve_contract(
    sequence_kind: str, input_type: str, analysis_mode: str
) -> tuple[InputType, AnalysisMode]:
    if input_type not in {"auto", "reads", "genome"}:
        raise InputValidationError("input_type must be one of: auto, reads, genome.")
    if analysis_mode not in {"auto", "reads", "genome", "assemble"}:
        raise InputValidationError(
            "analysis_mode must be one of: auto, reads, genome, assemble."
        )
    detected_type: InputType = "reads" if sequence_kind == "fastq" else "genome"
    resolved_type: InputType = (
        detected_type if input_type == "auto" else input_type  # type: ignore[assignment]
    )
    if resolved_type != detected_type:
        raise InputValidationError(
            f"Explicit input_type '{resolved_type}' does not match detected "
            f"{sequence_kind.upper()} content ({detected_type})."
        )
    if analysis_mode == "auto":
        resolved_mode: AnalysisMode = (
            "assemble" if resolved_type == "reads" else "genome"
        )
    else:
        resolved_mode = analysis_mode  # type: ignore[assignment]
    allowed_modes = {"reads", "assemble"} if resolved_type == "reads" else {"genome"}
    if resolved_mode not in allowed_modes:
        raise InputValidationError(
            f"input_type '{resolved_type}' does not support analysis_mode "
            f"'{resolved_mode}'."
        )
    return resolved_type, resolved_mode


def validate_inputs(
    files: Sequence[Path],
    output: Path,
    sample_id: str | None = None,
    *,
    input_type: str = "auto",
    analysis_mode: str = "auto",
) -> InputSet:
    """Validate count, identity, content type, and output safety."""
    if not files:
        raise InputValidationError("Provide one FASTA/FASTQ file or a paired FASTQ pair.")
    if len(files) > 2:
        raise InputValidationError("At most two input files are accepted.")
    resolved = tuple(Path(item).expanduser().resolve() for item in files)
    if len(set(resolved)) != len(resolved):
        raise InputValidationError("Duplicate input files are not allowed.")
    kinds = tuple(detect_sequence_format(path) for path in resolved)
    if len(set(kinds)) != 1:
        raise InputValidationError("Mixed FASTA and FASTQ input is not allowed.")
    if kinds[0] == "fasta" and len(resolved) != 1:
        raise InputValidationError("FASTA mode accepts exactly one assembled metagenome.")
    if kinds[0] == "fastq":
        _validate_pair(resolved)
    resolved_type, resolved_mode = _resolve_contract(
        kinds[0], input_type, analysis_mode
    )
    output_resolved = Path(output).expanduser().resolve()
    if output_resolved.exists() and not output_resolved.is_dir():
        raise InputValidationError(f"Output path is an existing file: {output_resolved}")
    for path in resolved:
        if output_resolved == path or output_resolved in path.parents:
            raise InputValidationError(
                f"Output directory would contain or overwrite an input file: {output_resolved}"
            )
    return InputSet(
        files=resolved,
        kind=kinds[0],
        paired=kinds[0] == "fastq" and len(resolved) == 2,
        compressed=tuple(is_gzip(path) for path in resolved),
        sample_id=sanitize_sample_id(sample_id) if sample_id else _derived_sample(resolved),
        input_type=resolved_type,
        analysis_mode=resolved_mode,
    )


def discover_samples(
    files: Sequence[Path],
    output: Path,
    *,
    input_directory: Path | None = None,
    sample_id: str | None = None,
    input_type: str = "auto",
    analysis_mode: str = "auto",
) -> list[InputSet]:
    """Discover independent FASTA samples and strict FASTQ singletons/pairs."""
    if files and input_directory is not None:
        raise InputValidationError("Use either input files or input_directory, not both.")
    candidates = [Path(item) for item in files]
    if input_directory is not None:
        directory = Path(input_directory).expanduser().resolve()
        if not directory.is_dir():
            raise InputValidationError(f"Input directory does not exist: {directory}")
        output_resolved = Path(output).expanduser().resolve()
        if directory == output_resolved or directory in output_resolved.parents:
            raise InputValidationError(
                "Output directory must not be inside the input directory."
            )
        candidates = sorted(
            (
                item
                for item in directory.iterdir()
                if item.is_file()
                and any(item.name.lower().endswith(suffix) for suffix in SUPPORTED_SUFFIXES)
            ),
            key=lambda item: item.name.casefold(),
        )
    if not candidates:
        raise InputValidationError("No supported FASTA/FASTQ input files were found.")
    resolved = [item.expanduser().resolve() for item in candidates]
    if len(set(resolved)) != len(resolved):
        raise InputValidationError("Duplicate input files are not allowed.")
    detected = {path: detect_sequence_format(path) for path in resolved}
    groups: list[list[Path]] = []
    groups.extend([[path] for path in resolved if detected[path] == "fasta"])
    paired: dict[str, dict[int, Path]] = {}
    for path in (item for item in resolved if detected[item] == "fastq"):
        key = _mate_key(path)
        if key is None:
            groups.append([path])
            continue
        stem, mate = key
        normalized = stem.casefold()
        slots = paired.setdefault(normalized, {})
        if mate in slots:
            raise InputValidationError(
                f"Duplicate R{mate} FASTQ files for sample stem '{stem or 'sample'}'."
            )
        slots[mate] = path
    for stem, slots in sorted(paired.items()):
        if set(slots) == {1}:
            groups.append([slots[1]])
            continue
        if set(slots) != {1, 2}:
            raise InputValidationError(
                f"FASTQ sample stem '{stem or 'sample'}' has R2 without R1."
            )
        groups.append([slots[1], slots[2]])
    groups.sort(key=lambda group: tuple(path.name.casefold() for path in group))
    if sample_id is not None and len(groups) != 1:
        raise InputValidationError(
            "--sample-id can only be used when exactly one sample is discovered."
        )
    samples = [
        validate_inputs(
            group,
            output,
            sample_id=sample_id,
            input_type=input_type,
            analysis_mode=analysis_mode,
        )
        for group in groups
    ]
    identifiers = [item.sample_id.casefold() for item in samples]
    if len(set(identifiers)) != len(identifiers):
        raise InputValidationError(
            "Discovered sample IDs are not unique; rename inputs or run samples "
            "separately with explicit --sample-id values."
        )
    return samples
