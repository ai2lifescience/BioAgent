"""Shared utilities."""

from __future__ import annotations

import sys
from pathlib import Path

from Bio import SeqIO


def collect_input_fastas(input_path: Path) -> dict[str, Path]:
    input_path = Path(input_path)
    if input_path.is_file():
        fastas = [input_path]
    else:
        fastas = [
            path
            for path in sorted(input_path.iterdir())
            if path.is_file() and path.suffix.lower() in {".fa", ".fasta", ".fna"}
        ]

    if not fastas:
        raise ValueError("no input genomes")

    return {path.stem: path for path in fastas}


def ensure_single_record(path: Path) -> None:
    n = sum(1 for _ in SeqIO.parse(Path(path), "fasta"))
    if n != 1:
        print("multi-record FASTA not supported in v1", file=sys.stderr)
        raise SystemExit(1)
