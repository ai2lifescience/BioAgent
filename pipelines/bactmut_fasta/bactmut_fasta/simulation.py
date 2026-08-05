"""Generate synthetic bacterial genomes with known SNP truth."""

import csv
import random
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

from .fasta import write_fasta
from .models import ReferenceGenome


CANONICAL = "ACGT"


def generate_simulated_samples(
    reference: ReferenceGenome,
    output_dir: Path,
    snp_rate: float,
    sample_count: int = 5,
    seed: int = 42,
) -> Tuple[List[Path], Set[int]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    eligible = [
        reference.offsets[name] + local_position
        for name, sequence in reference.records.items()
        for local_position, base in enumerate(sequence)
        if base in CANONICAL
    ]
    mutation_count = min(len(eligible), max(1, round(len(eligible) * snp_rate)))
    rng = random.Random(seed)
    paths: List[Path] = []
    truth_union: Set[int] = set()
    truth_rows: List[Tuple[str, int, str, str]] = []
    for sample_index in range(1, sample_count + 1):
        sample_name = f"simulated_{sample_index:03d}"
        selected = rng.sample(eligible, mutation_count)
        mutations: Dict[int, str] = {}
        for position in selected:
            reference_base = reference.base(position)
            alternate = rng.choice([base for base in CANONICAL if base != reference_base])
            mutations[position] = alternate
            truth_union.add(position)
            truth_rows.append((sample_name, position + 1, reference_base, alternate))
        records = []
        for record_name, sequence in reference.records.items():
            offset = reference.offsets[record_name]
            mutable = list(sequence)
            for global_position, alternate in mutations.items():
                local_position = global_position - offset
                if 0 <= local_position < len(mutable):
                    mutable[local_position] = alternate
            records.append((record_name, "".join(mutable)))
        path = output_dir / f"{sample_name}.fasta"
        write_fasta(records, path)
        paths.append(path)
    with (output_dir / "simulation_truth.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample", "reference_position", "reference_base", "alternate_base"])
        writer.writerows(truth_rows)
    return paths, truth_union

