"""Filtered SNP matrix generation."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .reference import ReferenceGenome
from .snippy_pipeline import SampleCalls


def build_snp_matrix(
    samples: Sequence[SampleCalls],
    reference: ReferenceGenome,
    positions: Sequence[int],
    output_tsv: Path,
) -> None:
    if not samples:
        raise ValueError("No samples available for SNP matrix")
    output_tsv = Path(output_tsv)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with output_tsv.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("pos\t" + "\t".join(sample.name for sample in samples) + "\n")
        for position in sorted(positions):
            reference_base = reference.base(position)
            calls = [sample.base_at(position, reference_base) for sample in samples]
            handle.write(f"{position + 1}\t" + "\t".join(calls) + "\n")
