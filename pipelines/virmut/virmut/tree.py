"""Tree-building stage."""

from __future__ import annotations

import subprocess
from pathlib import Path


class InsufficientSamplesForTreeError(ValueError):
    """Raised when a SNP matrix has too few samples for tree inference."""


def run_iqtree(
    matrix_tsv: Path,
    output_prefix: Path,
    model: str = "GTR+G",
) -> None:
    with Path(matrix_tsv).open(encoding="utf-8") as matrix_file:
        header = next(matrix_file).rstrip("\n").split("\t")
        samples = header[1:]
        rows = [
            (int(fields[0]), fields[1:])
            for line in matrix_file
            if line.strip()
            for fields in [line.rstrip("\n").split("\t")]
        ]

    if not rows:
        raise ValueError("no variant positions")
    if len(samples) < 3:
        raise InsufficientSamplesForTreeError(
            f"at least three samples are required for IQ-TREE; found {len(samples)}"
        )

    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    alignment_fasta = output_prefix.with_suffix(".fasta")
    rows.sort(key=lambda row: row[0])
    with alignment_fasta.open("w", encoding="utf-8") as out:
        for index, sample in enumerate(samples):
            sequence = "".join(values[index] for _, values in rows)
            out.write(f">{sample}\n{sequence}\n")

    subprocess.run(
        [
            "iqtree",
            "-s",
            str(alignment_fasta),
            "-st",
            "DNA",
            "-m",
            model,
            "-pre",
            str(output_prefix),
            "-redo",
        ],
        check=True,
    )
