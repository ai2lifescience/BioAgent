"""Pipeline output writers."""

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Set

from .fasta import write_fasta
from .models import FilterResult, ReferenceGenome, SampleCalls


GENETIC_CODE = {
    "TTT": "F",
    "TTC": "F",
    "TTA": "L",
    "TTG": "L",
    "TCT": "S",
    "TCC": "S",
    "TCA": "S",
    "TCG": "S",
    "TAT": "Y",
    "TAC": "Y",
    "TAA": "*",
    "TAG": "*",
    "TGT": "C",
    "TGC": "C",
    "TGA": "*",
    "TGG": "W",
    "CTT": "L",
    "CTC": "L",
    "CTA": "L",
    "CTG": "L",
    "CCT": "P",
    "CCC": "P",
    "CCA": "P",
    "CCG": "P",
    "CAT": "H",
    "CAC": "H",
    "CAA": "Q",
    "CAG": "Q",
    "CGT": "R",
    "CGC": "R",
    "CGA": "R",
    "CGG": "R",
    "ATT": "I",
    "ATC": "I",
    "ATA": "I",
    "ATG": "M",
    "ACT": "T",
    "ACC": "T",
    "ACA": "T",
    "ACG": "T",
    "AAT": "N",
    "AAC": "N",
    "AAA": "K",
    "AAG": "K",
    "AGT": "S",
    "AGC": "S",
    "AGA": "R",
    "AGG": "R",
    "GTT": "V",
    "GTC": "V",
    "GTA": "V",
    "GTG": "V",
    "GCT": "A",
    "GCC": "A",
    "GCA": "A",
    "GCG": "A",
    "GAT": "D",
    "GAC": "D",
    "GAA": "E",
    "GAG": "E",
    "GGT": "G",
    "GGC": "G",
    "GGA": "G",
    "GGG": "G",
}


@dataclass(frozen=True)
class VariantEvent:
    pos: int
    ref: str
    alt: str
    variant_type: str
    region: str


def write_initial_snp_list(
    path: Path,
    reference: ReferenceGenome,
    samples: Sequence[SampleCalls],
    positions: Sequence[int],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = ["reference_position", "reference_base", "covered_samples"]
        for sample in samples:
            header.extend([sample.name, f"{sample.name}_covered"])
        writer.writerow(header)
        for position in positions:
            reference_base = reference.base(position)
            row = [
                position + 1,
                reference_base,
                sum(sample.is_covered(position) for sample in samples),
            ]
            for sample in samples:
                row.extend(
                    [
                        sample.base_at(position, reference_base),
                        "yes" if sample.is_covered(position) else "no",
                    ]
                )
            writer.writerow(row)


def write_snp_matrix(
    path: Path,
    reference: ReferenceGenome,
    samples: Sequence[SampleCalls],
    positions: Sequence[int],
) -> None:
    records = []
    for sample in samples:
        sequence = "".join(
            sample.base_at(position, reference.base(position)) for position in positions
        )
        records.append((sample.name, sequence))
    write_fasta(records, path)


def write_mutation_report(
    path: Path,
    reference: ReferenceGenome,
    samples: Sequence[SampleCalls],
    result: FilterResult,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "reference_position",
                "reference_base",
                "alternate_base",
                "strain_count",
                "filtered",
                "filter_reason",
            ]
        )
        for position in result.initial_positions:
            reference_base = reference.base(position)
            alternate_bases = sorted(
                {
                    sample.variants[position]
                    for sample in samples
                    if position in sample.variants and sample.variants[position] != "N"
                }
            )
            if position in result.coverage_removed:
                filtered, reason = "yes", "insufficient_coverage"
            elif position in result.recombination_removed:
                filtered, reason = "yes", "recombination_region"
            else:
                filtered, reason = "no", ""
            for alternate in alternate_bases:
                writer.writerow(
                    [
                        position + 1,
                        reference_base,
                        alternate,
                        sum(sample.variants.get(position) == alternate for sample in samples),
                        filtered,
                        reason,
                    ]
                )


def write_variants_table(
    variants_path,
    reference,
    samples,
    result,
    summary_path,
) -> None:
    sample_events: Dict[str, Dict[int, VariantEvent]] = {}
    for sample in samples:
        events = (
            _events_from_paf(sample.paf_path, reference)
            if sample.paf_path is not None
            else []
        )
        sample_events[sample.name] = {}
        for event in events:
            sample_events[sample.name].setdefault(event.pos, event)

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
            ]
        )
        for position in sorted(result.final_positions):
            region, _, _ = _contig_for_position(reference, position)
            reference_base = reference.base(position)
            event = _event_for_position(position, samples, sample_events)
            if event is None:
                event = VariantEvent(position, reference_base, "NA", "UNKNOWN", region)
            ref_codon, ref_aa, alt_codon, alt_aa, effect = _annotate_event(
                event,
                reference,
            )
            effects[effect] += 1
            writer.writerow(
                [
                    region,
                    position + 1,
                    event.ref,
                    *[
                        sample.base_at(position, reference_base)
                        for sample in samples
                    ],
                    event.variant_type,
                    ref_codon,
                    ref_aa,
                    alt_codon,
                    alt_aa,
                    effect,
                ]
            )

    summary_path = Path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write(f"unique_variant_positions\t{len(result.final_positions)}\n")
        for effect in sorted(effects):
            handle.write(f"{effect}\t{effects[effect]}\n")


def _event_for_position(
    position: int,
    samples: Sequence[SampleCalls],
    sample_events: Mapping[str, Mapping[int, VariantEvent]],
) -> Optional[VariantEvent]:
    for sample in samples:
        event = sample_events.get(sample.name, {}).get(position)
        if event is not None:
            return event
    return None


def _events_from_paf(
    paf: Path,
    reference: ReferenceGenome,
) -> Sequence[VariantEvent]:
    if not paf.is_file():
        return []

    events = []
    with paf.open(encoding="utf-8") as paf_file:
        for line in paf_file:
            if not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 12:
                continue
            region = fields[5]
            if region not in reference.records:
                raise ValueError(f"PAF refers to unknown reference record: {region}")
            cs_tag = next(
                (field[5:] for field in fields[12:] if field.startswith("cs:Z:")),
                None,
            )
            if cs_tag is not None:
                events.extend(
                    _events_from_cs(
                        cs_tag,
                        int(fields[7]),
                        reference.records[region],
                        reference.offsets[region],
                        region,
                    )
                )
    return events


def _events_from_cs(
    cs: str,
    ref_start: int,
    reference_seq: str,
    global_offset: int,
    region: str,
) -> Sequence[VariantEvent]:
    events = []
    i = 0
    ref_pos = ref_start
    while i < len(cs):
        op = cs[i]
        if op == ":":
            i += 1
            start = i
            while i < len(cs) and cs[i].isdigit():
                i += 1
            ref_pos += int(cs[start:i])
        elif op == "*":
            if i + 2 >= len(cs):
                break
            alt_base = cs[i + 2].upper()
            events.append(
                VariantEvent(
                    global_offset + ref_pos,
                    reference_seq[ref_pos].upper(),
                    alt_base,
                    "SNP",
                    region,
                )
            )
            ref_pos += 1
            i += 3
        elif op in {"+", "-"}:
            sequence, i = _read_cs_indel_sequence(cs, i + 1, reference_seq, ref_pos, op)
            if not sequence:
                continue
            if op == "+":
                events.append(
                    VariantEvent(
                        global_offset + max(ref_pos - 1, 0),
                        "-",
                        sequence,
                        "INSERTION",
                        region,
                    )
                )
            else:
                deleted = reference_seq[ref_pos : ref_pos + len(sequence)].upper()
                events.append(
                    VariantEvent(
                        global_offset + ref_pos,
                        deleted,
                        "-",
                        "DELETION",
                        region,
                    )
                )
                ref_pos += len(sequence)
        elif op == "=":
            i += 1
            start = i
            while i < len(cs) and cs[i].isalpha():
                i += 1
            ref_pos += i - start
        else:
            i += 1
    return events


def _read_cs_indel_sequence(
    cs: str,
    index: int,
    reference_seq: str,
    ref_pos: int,
    op: str,
) -> tuple[str, int]:
    length_start = index
    while index < len(cs) and cs[index].isdigit():
        index += 1
    length = int(cs[length_start:index]) if index > length_start else None
    sequence_start = index
    while index < len(cs) and cs[index].isalpha():
        index += 1
    sequence = cs[sequence_start:index].upper()
    if not sequence and length is not None and op == "-":
        sequence = reference_seq[ref_pos : ref_pos + length].upper()
    return sequence, index


def _annotate_event(
    event: VariantEvent,
    reference: ReferenceGenome,
) -> tuple[str, str, str, str, str]:
    if event.variant_type == "UNKNOWN":
        return "NA", "NA", "NA", "NA", "NA"
    if event.variant_type == "INSERTION":
        effect = "inframe_insertion" if len(event.alt) % 3 == 0 else "frameshift"
        return "NA", "NA", "NA", "NA", effect
    if event.variant_type == "DELETION":
        effect = "inframe_deletion" if len(event.ref) % 3 == 0 else "frameshift"
        return "NA", "NA", "NA", "NA", effect
    if event.variant_type != "SNP":
        return "NA", "NA", "NA", "NA", "frameshift"

    reference_seq = reference.records[event.region]
    contig_offset = reference.offsets[event.region]
    local_position = event.pos - contig_offset
    codon_start = (local_position // 3) * 3
    ref_codon = reference_seq[codon_start : codon_start + 3].upper()
    if len(ref_codon) != 3:
        return "NA", "NA", "NA", "NA", "NA"
    offset = local_position % 3
    alt_codon = ref_codon[:offset] + event.alt + ref_codon[offset + 1 :]
    ref_aa = _translate(ref_codon)
    alt_aa = _translate(alt_codon)
    if ref_aa == alt_aa:
        effect = "synonymous"
    elif ref_aa != "*" and alt_aa == "*":
        effect = "stop_gained"
    elif ref_aa == "*" and alt_aa != "*":
        effect = "stop_lost"
    else:
        effect = "nonsynonymous"
    return ref_codon, ref_aa, alt_codon, alt_aa, effect


def _translate(codon: str) -> str:
    return GENETIC_CODE.get(codon.upper(), "X")


def _contig_for_position(
    reference: ReferenceGenome,
    global_position: int,
) -> tuple[str, int, str]:
    for name, offset in reference.offsets.items():
        sequence = reference.records[name]
        if offset <= global_position < offset + len(sequence):
            return name, offset, sequence
    raise IndexError(global_position)


def _ratio(removed: int, starting: int) -> str:
    return f"{(100.0 * removed / starting):.2f}%" if starting else "0.00%"


def write_summary(
    path: Path,
    sample_count: int,
    result: FilterResult,
    timings: Mapping[str, float],
    arguments: Mapping[str, object],
    aligner: str,
    tree_status: str,
    validation: Optional[Mapping[str, float]] = None,
) -> None:
    initial = len(result.initial_positions)
    after_coverage = len(result.coverage_positions)
    final = len(result.final_positions)
    lines = [
        "Bacterial genome comparison and mutation detection summary",
        "=" * 58,
        f"Input strain count: {sample_count}",
        f"Alignment backend: {aligner}",
        f"Initial unique SNP positions: {initial}",
        (
            f"After coverage filter (>= {float(arguments['min_coverage']) * 100:g}% strains): "
            f"{after_coverage}; removed {initial - after_coverage} "
            f"({_ratio(initial - after_coverage, initial)})"
        ),
        (
            f"After recombination sliding-window filter: {final}; removed "
            f"{after_coverage - final} ({_ratio(after_coverage - final, after_coverage)})"
        ),
        f"Final SNPs used for tree building: {final}",
        f"Recombination candidate regions: {len(result.recombination_regions)}",
        f"Window density mean: {result.window_mean:.8f}",
        f"Window density standard deviation: {result.window_sd:.8f}",
        f"Tree building: {tree_status}",
        "",
        "Runtime by step (seconds)",
        "-" * 25,
    ]
    for name, seconds in timings.items():
        lines.append(f"{name}: {seconds:.3f}")
    lines.extend(["", "Command-line arguments", "-" * 22])
    for key, value in arguments.items():
        lines.append(f"--{key.replace('_', '-')}: {value}")
    if validation is not None:
        lines.extend(
            [
                "",
                "Simulation validation",
                "-" * 21,
                f"True unique SNPs: {int(validation['true_snps'])}",
                f"Detected unique SNPs: {int(validation['detected_snps'])}",
                f"True-positive SNPs: {int(validation['true_positives'])}",
                f"Recovery Rate: {validation['recovery_rate']:.6f}",
                f"Precision: {validation['precision']:.6f}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
