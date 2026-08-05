"""Consensus SNP stage."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq


@dataclass(frozen=True)
class VariantEvent:
    pos: int
    ref: str
    alt: str
    variant_type: str


def call_snps(
    paf: Path,
    reference: Path,
    output_tsv: Path,
) -> None:
    reference_record = next(SeqIO.parse(Path(reference), "fasta"))
    reference_seq = str(reference_record.seq).upper()
    output_tsv = Path(output_tsv)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)

    saw_alignment = False
    rows: list[tuple[int, str, str]] = []
    with Path(paf).open(encoding="utf-8") as paf_file:
        for line in paf_file:
            if not line.strip():
                continue
            saw_alignment = True
            fields = line.rstrip("\n").split("\t")
            ref_pos = int(fields[7])
            cs_tag = next((field[5:] for field in fields[12:] if field.startswith("cs:Z:")), None)
            if cs_tag is None:
                continue
            rows.extend(_snps_from_cs(cs_tag, ref_pos, reference_seq))

    if not saw_alignment:
        raise ValueError("no alignments in PAF")

    with output_tsv.open("w", encoding="utf-8") as out:
        out.write("pos\tref\talt\n")
        for pos, ref, alt in rows:
            out.write(f"{pos}\t{ref}\t{alt}\n")


def _snps_from_cs(
    cs: str,
    ref_start: int,
    reference_seq: str,
) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
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
            ref_base = cs[i + 1].upper()
            alt_base = cs[i + 2].upper()
            rows.append((ref_pos + 1, reference_seq[ref_pos].upper(), alt_base))
            ref_pos += 1
            i += 3
        else:
            i += 1
    return rows


def build_variants_table(
    pafs: dict[str, Path] | None,
    reference: Path,
    output_tsv: Path,
    output_summary: Path,
    ivar_variants: Mapping[str, Mapping[int, Any]] | None = None,
) -> None:
    reference_record = next(SeqIO.parse(Path(reference), "fasta"))
    reference_seq = str(reference_record.seq).upper()
    if ivar_variants is not None:
        sample_events = {
            sample: [
                _event_from_ivar_variant(pos, variant)
                for pos, variant in variants.items()
            ]
            for sample, variants in ivar_variants.items()
        }
        samples = list(ivar_variants)
    else:
        pafs = pafs or {}
        sample_events = {
            sample: _events_from_paf(paf, reference_seq)
            for sample, paf in pafs.items()
        }
        samples = list(pafs)

    first_events: dict[int, VariantEvent] = {}
    calls: dict[str, dict[int, VariantEvent]] = {}
    for sample, events in sample_events.items():
        calls[sample] = {}
        for event in events:
            calls[sample].setdefault(event.pos, event)
            first_events.setdefault(event.pos, event)

    output_tsv = Path(output_tsv)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    fastq_columns = _ivar_sample_columns(samples) if ivar_variants is not None else []
    effects: Counter[str] = Counter()
    with output_tsv.open("w", encoding="utf-8") as out:
        columns = [
            "REGION",
            "POS",
            "REF",
            *samples,
            "VARIANT_TYPE",
            "REF_CODON",
            "REF_AA",
            "ALT_CODON",
            "ALT_AA",
            "EFFECT",
            *fastq_columns,
        ]
        out.write("\t".join(columns) + "\n")
        for pos in sorted(first_events):
            event = first_events[pos]
            ref_codon, ref_aa, alt_codon, alt_aa, effect = _annotate_event(
                event,
                reference_seq,
            )
            effects[effect] += 1
            sample_bases = [
                calls[sample].get(pos, event).alt
                if pos in calls[sample]
                else event.ref
                for sample in samples
            ]
            row = [
                reference_record.id,
                str(pos),
                event.ref,
                *sample_bases,
                event.variant_type,
                ref_codon,
                ref_aa,
                alt_codon,
                alt_aa,
                effect,
                *_ivar_sample_values(samples, ivar_variants, pos),
            ]
            out.write("\t".join(row) + "\n")

    output_summary = Path(output_summary)
    output_summary.parent.mkdir(parents=True, exist_ok=True)
    with output_summary.open("w", encoding="utf-8") as out:
        out.write(f"unique_variant_positions\t{len(first_events)}\n")
        for effect in sorted(effects):
            out.write(f"{effect}\t{effects[effect]}\n")


def _events_from_paf(paf: Path, reference_seq: str) -> list[VariantEvent]:
    events: list[VariantEvent] = []
    with Path(paf).open(encoding="utf-8") as paf_file:
        for line in paf_file:
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 13:
                continue
            cs_tag = next(
                (field[5:] for field in fields[12:] if field.startswith("cs:Z:")),
                None,
            )
            if cs_tag is not None:
                events.extend(_events_from_cs(cs_tag, int(fields[7]), reference_seq))
    return events


def _event_from_ivar_variant(pos: int, variant: Any) -> VariantEvent:
    event_pos = int(_variant_value(variant, "pos", default=str(pos)))
    ref = _variant_value(variant, "ref").upper()
    alt = _variant_value(variant, "alt").upper()

    if alt.startswith("+"):
        return VariantEvent(event_pos, "-", alt[1:] or "N", "INSERTION")
    if alt.startswith("-"):
        return VariantEvent(event_pos, alt[1:] or ref, "-", "DELETION")
    if alt == "-":
        return VariantEvent(event_pos, ref, "-", "DELETION")
    if ref == "-":
        return VariantEvent(event_pos, "-", alt, "INSERTION")
    if len(ref) == 1 and len(alt) == 1:
        return VariantEvent(event_pos, ref, alt, "SNP")
    if len(ref) < len(alt):
        return VariantEvent(event_pos, "-", alt[len(ref) :] or alt, "INSERTION")
    if len(ref) > len(alt):
        return VariantEvent(event_pos, ref[len(alt) :] or ref, "-", "DELETION")
    return VariantEvent(event_pos, ref, alt, "MNP")


def _ivar_sample_columns(samples: list[str]) -> list[str]:
    columns: list[str] = []
    for sample in samples:
        columns.extend(
            [
                f"{sample}_ALT_FREQ",
                f"{sample}_DEPTH",
                f"{sample}_PVAL",
                f"{sample}_PASS",
            ]
        )
    return columns


def _ivar_sample_values(
    samples: list[str],
    ivar_variants: Mapping[str, Mapping[int, Any]] | None,
    pos: int,
) -> list[str]:
    if ivar_variants is None:
        return []

    values: list[str] = []
    for sample in samples:
        variant = ivar_variants[sample].get(pos)
        if variant is None:
            values.extend(["NA", "NA", "NA", "NA"])
        else:
            values.extend(
                [
                    _variant_value(variant, "alt_freq"),
                    _variant_value(variant, "total_depth"),
                    _variant_value(variant, "pval"),
                    _variant_value(variant, "pass_filter"),
                ]
            )
    return values


def _variant_value(variant: Any, name: str, default: str = "NA") -> str:
    value: Any
    if isinstance(variant, Mapping):
        value = variant.get(name, variant.get(name.upper(), default))
    else:
        value = getattr(variant, name, default)
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _events_from_cs(
    cs: str,
    ref_start: int,
    reference_seq: str,
) -> list[VariantEvent]:
    events: list[VariantEvent] = []
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
            events.append(
                VariantEvent(ref_pos + 1, reference_seq[ref_pos], cs[i + 2].upper(), "SNP")
            )
            ref_pos += 1
            i += 3
        elif op in {"+", "-"}:
            i += 1
            start = i
            while i < len(cs) and cs[i].isalpha():
                i += 1
            sequence = cs[start:i].upper()
            if op == "+":
                events.append(VariantEvent(max(ref_pos, 1), "-", sequence, "INSERTION"))
            else:
                deleted = reference_seq[ref_pos : ref_pos + len(sequence)]
                events.append(VariantEvent(ref_pos + 1, deleted, "-", "DELETION"))
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


def _annotate_event(
    event: VariantEvent,
    reference_seq: str,
) -> tuple[str, str, str, str, str]:
    # Assembled single-record FASTA consensus mode: annotations are derived
    # only from observed sequence events and the reference sequence.
    if event.variant_type == "INSERTION":
        effect = "inframe_insertion" if len(event.alt) % 3 == 0 else "frameshift"
        return "NA", "NA", "NA", "NA", effect
    if event.variant_type == "DELETION":
        effect = "inframe_deletion" if len(event.ref) % 3 == 0 else "frameshift"
        return "NA", "NA", "NA", "NA", effect
    if event.variant_type != "SNP":
        return "NA", "NA", "NA", "NA", "frameshift"

    codon_start = ((event.pos - 1) // 3) * 3
    ref_codon = reference_seq[codon_start : codon_start + 3]
    if len(ref_codon) != 3:
        return "NA", "NA", "NA", "NA", "NA"
    offset = (event.pos - 1) % 3
    alt_codon = ref_codon[:offset] + event.alt + ref_codon[offset + 1 :]
    ref_aa = str(Seq(ref_codon).translate(table=1))
    alt_aa = str(Seq(alt_codon).translate(table=1))
    if ref_aa == alt_aa:
        effect = "synonymous"
    elif ref_aa != "*" and alt_aa == "*":
        effect = "stop_gained"
    elif ref_aa == "*" and alt_aa != "*":
        effect = "stop_lost"
    else:
        effect = "nonsynonymous"
    return ref_codon, ref_aa, alt_codon, alt_aa, effect
