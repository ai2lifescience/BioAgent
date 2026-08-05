"""Variant and summary reports for Snippy calls."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .filtering import FilterResult
from .reference import ReferenceGenome
from .snippy_pipeline import SampleCalls, BcftoolsVariant


GENETIC_CODE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
COMPLEMENT = str.maketrans("ACGT", "TGCA")
POSITION_RE = re.compile(r"^(\d+)(?:/\d+)?$")


def write_variants_table(
    variants_path: Path,
    reference: ReferenceGenome,
    samples: Sequence[SampleCalls],
    result: FilterResult,
    summary_path: Path,
) -> None:
    variants_path = Path(variants_path)
    variants_path.parent.mkdir(parents=True, exist_ok=True)
    effects: Counter[str] = Counter()
    with variants_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "REGION",
                "POS",
                "REF",
                *[sample.name for sample in samples],
                "VARIANT_TYPE",
                "REF_CODON",
                "REF_AA",
                "ALT_CODON",
                "ALT_AA",
                "EFFECT",
                *[
                    column
                    for sample in samples
                    for column in (
                        f"{sample.name}_ALT_FREQ",
                        f"{sample.name}_DEPTH",
                        f"{sample.name}_PVAL",
                        f"{sample.name}_PASS",
                    )
                ],
            ]
        )
        for position in sorted(result.final_positions):
            event = _event_for_position(position, samples)
            if event is None:
                region, local_position, _ = reference.location(position)
                pos = local_position + 1
                ref = reference.base(position)
                variant_type = "UNKNOWN"
                annotation = ("NA", "NA", "NA", "NA")
                effect = "NA"
            else:
                region = event.region
                pos = event.pos
                ref = event.ref
                variant_type = event.variant_type
                annotation = _codon_annotation(event, reference)
                effect = event.effect
                if effect == "NA":
                    effect = _effect_annotation(annotation)
            effects[effect] += 1
            reference_base = reference.base(position)
            metadata = []
            for sample in samples:
                sample_event = sample.variant_info.get(position)
                if sample_event is None:
                    metadata.extend(["NA", "NA", "NA", "NA"])
                else:
                    metadata.extend(
                        [
                            sample_event.alt_freq,
                            sample_event.depth,
                            sample_event.pval,
                            sample_event.pass_filter,
                        ]
                    )
            writer.writerow(
                [
                    region,
                    pos,
                    ref,
                    *[sample.base_at(position, reference_base) for sample in samples],
                    variant_type,
                    *annotation,
                    effect,
                    *metadata,
                ]
            )

    summary_path = Path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"initial_variant_positions\t{len(result.initial_positions)}\n")
        handle.write(f"after_coverage_filter\t{len(result.coverage_positions)}\n")
        handle.write(f"after_recombination_filter\t{len(result.final_positions)}\n")
        handle.write(f"coverage_removed\t{len(result.coverage_removed)}\n")
        handle.write(f"recombination_removed\t{len(result.recombination_removed)}\n")
        for effect in sorted(effects):
            handle.write(f"{effect}\t{effects[effect]}\n")


def _event_for_position(
    position: int,
    samples: Sequence[SampleCalls],
) -> Optional[BcftoolsVariant]:
    for sample in samples:
        event = sample.variant_info.get(position)
        if event is not None:
            return event
    return None


def _codon_annotation(
    event: BcftoolsVariant,
    reference: ReferenceGenome,
) -> Tuple[str, str, str, str]:
    if (
        event.variant_type != "SNP"
        or len(event.ref) != 1
        or len(event.alt) != 1
        or event.strand not in {"+", "-"}
    ):
        return "NA", "NA", "NA", "NA"

    _, local_position, sequence = reference.location(event.global_pos)
    if event.nt_pos == "NA":
        coding_position = local_position + 1
    else:
        match = POSITION_RE.fullmatch(event.nt_pos)
        if match is None:
            return "NA", "NA", "NA", "NA"
        coding_position = int(match.group(1))
    offset_in_codon = (coding_position - 1) % 3
    if event.strand == "+":
        codon_start = local_position - offset_in_codon
        if codon_start < 0:
            return "NA", "NA", "NA", "NA"
        ref_codon = sequence[codon_start : codon_start + 3].upper()
        if len(ref_codon) != 3:
            return "NA", "NA", "NA", "NA"
        alt_codon = (
            ref_codon[:offset_in_codon]
            + event.alt
            + ref_codon[offset_in_codon + 1 :]
        )
    else:
        genomic_positions = [
            local_position + offset_in_codon - index for index in range(3)
        ]
        if min(genomic_positions) < 0 or max(genomic_positions) >= len(sequence):
            return "NA", "NA", "NA", "NA"
        ref_codon = "".join(
            sequence[position].translate(COMPLEMENT) for position in genomic_positions
        ).upper()
        coding_alt = event.alt.translate(COMPLEMENT)
        alt_codon = (
            ref_codon[:offset_in_codon]
            + coding_alt
            + ref_codon[offset_in_codon + 1 :]
        )
    if set(ref_codon + alt_codon) - set("ACGT"):
        return "NA", "NA", "NA", "NA"
    return (
        ref_codon,
        GENETIC_CODE.get(ref_codon, "X"),
        alt_codon,
        GENETIC_CODE.get(alt_codon, "X"),
    )


def _effect_annotation(annotation: Tuple[str, str, str, str]) -> str:
    _, ref_aa, _, alt_aa = annotation
    if "NA" in annotation or "X" in (ref_aa, alt_aa):
        return "NA"
    if ref_aa != "*" and alt_aa == "*":
        return "stop_gained"
    if ref_aa == "*" and alt_aa != "*":
        return "stop_lost"
    if ref_aa == alt_aa:
        return "synonymous"
    return "nonsynonymous"
