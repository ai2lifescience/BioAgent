"""Mutation matrix stage."""

from __future__ import annotations

from pathlib import Path


def build_snp_matrix(
    snp_tsvs: dict[str, Path],
    output_tsv: Path,
) -> None:
    if not snp_tsvs:
        raise ValueError("no snp tables")

    output_tsv = Path(output_tsv)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)

    sample_calls: dict[str, dict[int, tuple[str, str]]] = {}
    refs: dict[int, str] = {}
    positions: set[int] = set()
    for sample, snp_tsv in snp_tsvs.items():
        calls: dict[int, tuple[str, str]] = {}
        with Path(snp_tsv).open(encoding="utf-8") as snp_file:
            next(snp_file, None)
            for line in snp_file:
                if not line.strip():
                    continue
                pos_text, ref, alt = line.rstrip("\n").split("\t")
                pos = int(pos_text)
                calls[pos] = (ref, alt)
                refs.setdefault(pos, ref)
                positions.add(pos)
        sample_calls[sample] = calls

    samples = list(snp_tsvs)
    with output_tsv.open("w", encoding="utf-8") as out:
        out.write("pos\t" + "\t".join(samples) + "\n")
        for pos in sorted(positions):
            values = []
            for sample in samples:
                if pos in sample_calls[sample]:
                    values.append(sample_calls[sample][pos][1])
                else:
                    values.append(refs[pos])
            out.write(f"{pos}\t" + "\t".join(values) + "\n")
