"""Assembly and gene-prediction quality metrics."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Sequence

from .errors import InputValidationError
from .input import open_sequence_text


def iter_fasta(path: Path) -> Iterator[tuple[str, str]]:
    """Yield validated FASTA identifiers and sequences."""
    identifier: str | None = None
    pieces: list[str] = []
    with open_sequence_text(path) as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if identifier is not None:
                    yield identifier, "".join(pieces)
                identifier = line[1:].split()[0]
                pieces = []
            elif identifier is None:
                raise InputValidationError(f"Sequence before FASTA header in {path}")
            else:
                pieces.append(line)
    if identifier is not None:
        yield identifier, "".join(pieces)



def fastq_qc(paths: Sequence[Path]) -> dict[str, float | int]:
    """Count reads and bases in validated plain or gzip FASTQ files."""
    read_count = 0
    base_count = 0
    for path in paths:
        file_lines = 0
        with open_sequence_text(path) as handle:
            for file_lines, raw in enumerate(handle, start=1):
                if file_lines % 4 == 2:
                    sequence = raw.strip()
                    if not sequence:
                        raise InputValidationError(f"Empty FASTQ sequence in {path}")
                    read_count += 1
                    base_count += len(sequence)
        if file_lines % 4:
            raise InputValidationError(f"Incomplete FASTQ record in {path}")
    return {
        "file_count": len(paths),
        "read_count": read_count,
        "base_count": base_count,
        "mean_read_length": round(base_count / read_count, 3) if read_count else 0.0,
    }

def assembly_qc(path: Path) -> dict[str, float | int]:
    """Calculate deterministic contig count, length, N50, and GC metrics."""
    lengths: list[int] = []
    gc = 0
    total = 0
    for _, sequence in iter_fasta(path):
        length = len(sequence)
        if length:
            lengths.append(length)
            total += length
            gc += sum(1 for base in sequence.upper() if base in {"G", "C"})
    if not lengths:
        raise InputValidationError(f"Assembly contains no non-empty contigs: {path}")
    threshold = total / 2
    cumulative = 0
    n50 = 0
    for length in sorted(lengths, reverse=True):
        cumulative += length
        if cumulative >= threshold:
            n50 = length
            break
    return {
        "contig_count": len(lengths),
        "total_length": total,
        "min_contig_length": min(lengths),
        "max_contig_length": max(lengths),
        "n50": n50,
        "gc_percent": round((gc / total) * 100, 6),
    }


def count_fasta_records(path: Path) -> int:
    """Count non-empty FASTA records."""
    return sum(1 for _ in iter_fasta(path))
