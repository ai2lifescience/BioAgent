#!/usr/bin/env python3
"""Full-artifact, dependency-light DNA sequencing pipeline demo for BioAgent."""

from __future__ import annotations

import csv
import base64
import gzip
import html
import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
import yaml


DNA_BASES = frozenset("ACGTN")
TRANSITIONS = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}


@dataclass(frozen=True)
class FastqRecord:
    identifier: str
    description: str
    sequence: str
    quality: str

    @property
    def scores(self) -> list[int]:
        return [ord(character) - 33 for character in self.quality]

    @property
    def mean_quality(self) -> float:
        return statistics.fmean(self.scores) if self.quality else 0.0

    @property
    def gc_percent(self) -> float:
        called = [base for base in self.sequence if base in "ACGT"]
        if not called:
            return 0.0
        return (called.count("G") + called.count("C")) / len(called) * 100


def fail(message: str) -> None:
    raise SystemExit(f"generic_bio: {message}")


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        fail("config must contain a YAML mapping")
    return config


def configured_path(config: dict[str, Any], key: str, config_dir: Path) -> Path:
    value = str(config.get(key) or "").strip()
    if not value:
        fail(f"config is missing {key}")
    path = Path(value).expanduser()
    return path if path.is_absolute() else config_dir / path


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        fail(f"input file not found: {path}")
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return handle.read().splitlines()


def parse_fastq(path: Path) -> list[FastqRecord]:
    lines = read_lines(path)
    if not lines or len(lines) % 4:
        fail(f"FASTQ must contain complete four-line records: {path}")

    records: list[FastqRecord] = []
    seen: set[str] = set()
    for offset in range(0, len(lines), 4):
        record_number = offset // 4 + 1
        header, raw_sequence, plus, quality = lines[offset : offset + 4]
        if not header.startswith("@") or not header[1:].strip():
            fail(f"invalid FASTQ header in record {record_number}")
        if not plus.startswith("+"):
            fail(f"invalid FASTQ separator in record {record_number}")
        description = header[1:].strip()
        identifier = description.split()[0]
        if identifier in seen:
            fail(f"duplicate FASTQ read ID: {identifier}")
        seen.add(identifier)
        sequence = raw_sequence.strip().upper()
        invalid = sorted(set(sequence) - DNA_BASES)
        if not sequence or invalid:
            detail = f"invalid base(s) {', '.join(invalid)}" if invalid else "empty sequence"
            fail(f"{detail} in FASTQ record {record_number}")
        if len(sequence) != len(quality):
            fail(f"sequence and quality lengths differ in FASTQ record {record_number}")
        if any(ord(character) < 33 or ord(character) > 126 for character in quality):
            fail(f"quality score outside printable Phred+33 range in record {record_number}")
        records.append(FastqRecord(identifier, description, sequence, quality))
    return records


def parse_reference(path: Path) -> tuple[str, str]:
    records: list[tuple[str, list[str]]] = []
    identifier = ""
    parts: list[str] = []
    for line_number, raw_line in enumerate(read_lines(path), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if identifier:
                records.append((identifier, parts))
            identifier = line[1:].strip().split()[0] if line[1:].strip() else ""
            if not identifier:
                fail(f"empty FASTA identifier at line {line_number}")
            parts = []
        else:
            if not identifier:
                fail(f"FASTA sequence occurs before a header at line {line_number}")
            parts.append(line.upper())
    if identifier:
        records.append((identifier, parts))
    if len(records) != 1:
        fail(f"reference FASTA must contain exactly one sequence; found {len(records)}")
    reference_id, sequence_parts = records[0]
    sequence = "".join(sequence_parts)
    invalid = sorted(set(sequence) - DNA_BASES)
    if not sequence or invalid:
        detail = f"invalid base(s) {', '.join(invalid)}" if invalid else "an empty sequence"
        fail(f"reference contains {detail}")
    return reference_id, sequence


def read_metadata(path: Path, sample_id: str) -> tuple[dict[str, str], list[str]]:
    if not path.is_file():
        fail(f"metadata table not found: {path}")
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        first_line = handle.readline()
        handle.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = [str(field) for field in (reader.fieldnames or [])]
        if "sample_id" not in fields:
            fail(f"metadata must contain sample_id; available columns: {', '.join(fields)}")
        matches: list[dict[str, str]] = []
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            row_id = str(row.get("sample_id") or "").strip()
            if not row_id:
                fail(f"metadata row {row_number} has an empty sample_id")
            if row_id in seen:
                fail(f"duplicate metadata sample_id at row {row_number}: {row_id}")
            seen.add(row_id)
            if row_id == sample_id:
                matches.append({field: str(row.get(field) or "").strip() for field in fields})
    if not matches:
        fail(f"sample_id '{sample_id}' was not found in metadata")
    return matches[0], fields


def validate_params(params: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(params.get("sample_id") or "").strip()
    if not sample_id:
        fail("params.sample_id must not be empty")
    try:
        values = {
            "sample_id": sample_id,
            "min_length": int(params.get("min_length", 0)),
            "min_mean_quality": float(params.get("min_mean_quality", 0)),
            "min_base_quality": int(params.get("min_base_quality", 0)),
            "min_alt_fraction": float(params.get("min_alt_fraction", 0.5)),
            "min_alt_depth": int(params.get("min_alt_depth", 1)),
            "plot_dpi": int(params.get("plot_dpi", 140)),
        }
    except (TypeError, ValueError) as exc:
        fail(f"invalid numeric parameter: {exc}")
    if values["min_length"] < 0:
        fail("params.min_length must be at least 0")
    if not 0 <= values["min_mean_quality"] <= 93:
        fail("params.min_mean_quality must be between 0 and 93")
    if not 0 <= values["min_base_quality"] <= 93:
        fail("params.min_base_quality must be between 0 and 93")
    if not 0.5 <= values["min_alt_fraction"] <= 1:
        fail("params.min_alt_fraction must be between 0.5 and 1")
    if values["min_alt_depth"] < 1:
        fail("params.min_alt_depth must be at least 1")
    if not 72 <= values["plot_dpi"] <= 600:
        fail("params.plot_dpi must be between 72 and 600")
    raw_emit_tree = params.get("emit_phylogenetic_tree", False)
    values["emit_phylogenetic_tree"] = (
        raw_emit_tree
        if isinstance(raw_emit_tree, bool)
        else str(raw_emit_tree).strip().lower() in {"1", "true", "yes", "on"}
    )
    return values


def filter_reason(record: FastqRecord, params: dict[str, Any]) -> str:
    reasons: list[str] = []
    if len(record.sequence) < params["min_length"]:
        reasons.append("short")
    if record.mean_quality < params["min_mean_quality"]:
        reasons.append("low_quality")
    return ",".join(reasons) if reasons else "pass"


def analyze_positions(
    reference: str,
    records: list[FastqRecord],
    params: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    consensus: list[str] = []
    variants: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    for index, reference_base in enumerate(reference):
        counts: Counter[str] = Counter()
        for record in records:
            if index >= len(record.sequence) or record.scores[index] < params["min_base_quality"]:
                continue
            base = record.sequence[index]
            if base in "ACGT":
                counts[base] += 1
        depth = sum(counts.values())
        if counts:
            top_count = max(counts.values())
            top_bases = sorted(base for base, count in counts.items() if count == top_count)
            consensus_base = reference_base if reference_base in top_bases else top_bases[0]
        else:
            consensus_base = reference_base
        consensus.append(consensus_base)

        variant: Optional[dict[str, Any]] = None
        alt_depth = counts.get(consensus_base, 0)
        alt_fraction = alt_depth / depth if depth else 0.0
        if (
            consensus_base != reference_base
            and alt_depth >= params["min_alt_depth"]
            and alt_fraction >= params["min_alt_fraction"]
        ):
            variant = {
                "position": index + 1,
                "ref": reference_base,
                "alt": consensus_base,
                "depth": depth,
                "ref_depth": counts.get(reference_base, 0),
                "alt_depth": alt_depth,
                "alt_fraction": alt_fraction,
                "change_type": (
                    "transition" if (reference_base, consensus_base) in TRANSITIONS else "transversion"
                ),
            }
            variants.append(variant)
        positions.append(
            {
                "chrom": "",
                "position": index + 1,
                "reference": reference_base,
                "depth": depth,
                "A": counts.get("A", 0),
                "C": counts.get("C", 0),
                "G": counts.get("G", 0),
                "T": counts.get("T", 0),
                "consensus": consensus_base,
                "variant": "yes" if variant else "no",
            }
        )
    return "".join(consensus), variants, positions


def quality_percent(records: list[FastqRecord], threshold: int) -> float:
    scores = [score for record in records for score in record.scores]
    return (sum(score >= threshold for score in scores) / len(scores) * 100) if scores else 0.0


def write_filtered_fastq(path: Path, records: list[FastqRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(f"@{record.description}\n{record.sequence}\n+\n{record.quality}\n")


def write_read_qc(path: Path, records: list[FastqRecord], statuses: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["read_id", "length", "gc_percent", "mean_quality", "q20_bases", "q30_bases", "status"]
        )
        for record in records:
            scores = record.scores
            writer.writerow(
                [
                    record.identifier,
                    len(record.sequence),
                    f"{record.gc_percent:.2f}",
                    f"{record.mean_quality:.2f}",
                    sum(score >= 20 for score in scores),
                    sum(score >= 30 for score in scores),
                    statuses[record.identifier],
                ]
            )


def write_sample_summary(
    path: Path,
    metadata: dict[str, str],
    metadata_fields: list[str],
    metrics: dict[str, Any],
) -> None:
    metric_fields = [
        "input_read_count",
        "passed_read_count",
        "read_retention_percent",
        "mean_input_read_length",
        "mean_input_quality",
        "q30_base_percent",
        "mean_retained_depth",
        "reference_coverage_percent",
        "variant_count",
    ]
    fields = metadata_fields + [field for field in metric_fields if field not in metadata_fields]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerow({**metadata, **{field: metrics[field] for field in metric_fields}})


def write_coverage(path: Path, reference_id: str, positions: list[dict[str, Any]]) -> None:
    fields = ["chrom", "position", "reference", "depth", "A", "C", "G", "T", "consensus", "variant"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for position in positions:
            writer.writerow({**position, "chrom": reference_id})


def write_alignment_sam(
    path: Path,
    reference_id: str,
    reference: str,
    sample_id: str,
    platform: str,
    records: list[FastqRecord],
) -> None:
    safe_platform = (platform or "unknown").replace("\t", "_").replace(" ", "_")
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("@HD\tVN:1.6\tSO:unknown\n")
        handle.write(f"@SQ\tSN:{reference_id}\tLN:{len(reference)}\n")
        handle.write(f"@RG\tID:{sample_id}\tSM:{sample_id}\tPL:{safe_platform}\n")
        for record in records:
            matched_length = min(len(record.sequence), len(reference))
            clipped_length = max(0, len(record.sequence) - matched_length)
            cigar = f"{matched_length}M" + (f"{clipped_length}S" if clipped_length else "")
            mismatches = sum(
                record.sequence[index] != reference[index]
                for index in range(matched_length)
                if record.sequence[index] in "ACGT" and reference[index] in "ACGT"
            )
            handle.write(
                f"{record.identifier}\t0\t{reference_id}\t1\t60\t{cigar}\t*\t0\t0\t"
                f"{record.sequence}\t{record.quality}\tRG:Z:{sample_id}\tNM:i:{mismatches}\n"
            )


def write_fasta(path: Path, identifier: str, sequence: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f">{identifier}\n")
        for offset in range(0, len(sequence), 80):
            handle.write(sequence[offset : offset + 80] + "\n")


def write_vcf(
    path: Path,
    reference_id: str,
    reference_length: int,
    sample_id: str,
    variants: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("##fileformat=VCFv4.2\n")
        handle.write("##source=generic_bio_positional_demo\n")
        handle.write(f"##contig=<ID={reference_id},length={reference_length}>\n")
        handle.write('##INFO=<ID=DP,Number=1,Type=Integer,Description="Read depth">\n')
        handle.write('##INFO=<ID=AF,Number=A,Type=Float,Description="Alternate allele fraction">\n')
        handle.write('##INFO=<ID=TYPE,Number=1,Type=String,Description="SNV change type">\n')
        handle.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Haploid genotype">\n')
        handle.write('##FORMAT=<ID=AD,Number=R,Type=Integer,Description="Allele depths">\n')
        handle.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + sample_id + "\n")
        for variant in variants:
            info = (
                f"DP={variant['depth']};AF={variant['alt_fraction']:.4f};"
                f"TYPE={variant['change_type']}"
            )
            sample = f"1:{variant['ref_depth']},{variant['alt_depth']}"
            handle.write(
                f"{reference_id}\t{variant['position']}\t.\t{variant['ref']}\t"
                f"{variant['alt']}\t.\tPASS\t{info}\tGT:AD\t{sample}\n"
            )


def write_variant_table(path: Path, reference_id: str, variants: list[dict[str, Any]]) -> None:
    fields = [
        "chrom",
        "position",
        "ref",
        "alt",
        "depth",
        "ref_depth",
        "alt_depth",
        "alt_fraction",
        "change_type",
        "filter",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for variant in variants:
            writer.writerow(
                {
                    "chrom": reference_id,
                    **variant,
                    "alt_fraction": f"{variant['alt_fraction']:.4f}",
                    "filter": "PASS",
                }
            )


def write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def style_figure(figure: Any) -> None:
    figure.patch.set_facecolor("white")
    figure.tight_layout()


def plot_qc(
    path: Path,
    records: list[FastqRecord],
    statuses: dict[str, str],
    params: dict[str, Any],
) -> None:
    passed = [record for record in records if statuses[record.identifier] == "pass"]
    failed = [record for record in records if statuses[record.identifier] != "pass"]
    figure, axes = plt.subplots(2, 2, figsize=(10, 7))
    axes[0, 0].hist(
        [[len(record.sequence) for record in passed], [len(record.sequence) for record in failed]],
        bins=max(3, min(15, len(records))),
        label=["Pass", "Fail"],
        color=["#2b8cbe", "#de2d26"],
    )
    axes[0, 0].axvline(params["min_length"], color="#444444", linestyle="--", linewidth=1)
    axes[0, 0].set(title="Read length", xlabel="Bases", ylabel="Reads")
    axes[0, 0].legend()

    axes[0, 1].hist(
        [record.mean_quality for record in records],
        bins=max(3, min(15, len(records))),
        color="#41ab5d",
    )
    axes[0, 1].axvline(params["min_mean_quality"], color="#444444", linestyle="--", linewidth=1)
    axes[0, 1].set(title="Mean read quality", xlabel="Phred score", ylabel="Reads")

    for group, group_records, offset, color in (
        ("Pass", passed, -0.15, "#2b8cbe"),
        ("Fail", failed, 0.15, "#de2d26"),
    ):
        axes[1, 0].scatter(
            [len(record.sequence) + offset for record in group_records],
            [record.gc_percent for record in group_records],
            color=color,
            edgecolors="white",
            linewidths=0.5,
            s=55,
            label=group,
        )
    axes[1, 0].set(title="Read GC by length", xlabel="Read length", ylabel="GC (%)", ylim=(0, 100))
    axes[1, 0].legend()

    reason_counts = Counter(statuses.values())
    labels = list(reason_counts)
    axes[1, 1].bar(labels, [reason_counts[label] for label in labels], color="#756bb1")
    axes[1, 1].set(title="Filter outcomes", xlabel="Status", ylabel="Reads")
    axes[1, 1].tick_params(axis="x", rotation=20)
    style_figure(figure)
    figure.savefig(path, dpi=params["plot_dpi"], bbox_inches="tight")
    plt.close(figure)


def plot_coverage(
    path: Path,
    positions: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    params: dict[str, Any],
) -> None:
    x_values = [position["position"] for position in positions]
    depths = [position["depth"] for position in positions]
    figure, axis = plt.subplots(figsize=(10, 4.5))
    axis.fill_between(x_values, depths, color="#9ecae1", alpha=0.7)
    axis.plot(x_values, depths, color="#2171b5", linewidth=1.8, label="High-quality depth")
    if depths:
        axis.axhline(statistics.fmean(depths), color="#444444", linestyle="--", label="Mean depth")
    if variants:
        variant_positions = [variant["position"] for variant in variants]
        variant_depths = [depths[position - 1] for position in variant_positions]
        axis.scatter(variant_positions, variant_depths, color="#de2d26", marker="D", label="Variant")
    axis.set(title="Reference coverage profile", xlabel="Reference position", ylabel="Read depth")
    axis.set_ylim(bottom=0)
    axis.legend()
    style_figure(figure)
    figure.savefig(path, dpi=params["plot_dpi"], bbox_inches="tight")
    plt.close(figure)


def plot_variants(path: Path, variants: list[dict[str, Any]], params: dict[str, Any]) -> None:
    figure, axis = plt.subplots(figsize=(9, 4.5))
    if variants:
        labels = [f"{variant['ref']}{variant['position']}{variant['alt']}" for variant in variants]
        fractions = [variant["alt_fraction"] * 100 for variant in variants]
        bars = axis.bar(labels, fractions, color="#ef6548")
        axis.bar_label(bars, fmt="%.1f%%", padding=3)
        axis.axhline(params["min_alt_fraction"] * 100, color="#444444", linestyle="--", label="Threshold")
        axis.set_ylim(0, 105)
        axis.legend()
    else:
        axis.text(0.5, 0.5, "No variants passed filters", ha="center", va="center", transform=axis.transAxes)
        axis.set_xticks([])
    axis.set(title="Variant allele fractions", xlabel="Variant", ylabel="Alternate allele fraction (%)")
    style_figure(figure)
    figure.savefig(path, dpi=params["plot_dpi"], bbox_inches="tight")
    plt.close(figure)


def newick_label(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._-" else "_" for character in value)
    return cleaned.strip("_") or "sequence"


def write_phylogenetic_tree(
    tree_path: Path,
    figure_path: Path,
    reference_id: str,
    reference: str,
    sample_id: str,
    consensus: str,
    params: dict[str, Any],
) -> None:
    compared = min(len(reference), len(consensus))
    mismatches = sum(reference[index] != consensus[index] for index in range(compared))
    distance = mismatches / compared if compared else 0.0
    branch_length = distance / 2
    reference_label = newick_label(reference_id)
    consensus_label = newick_label(f"{sample_id}_consensus")
    newick = f"({reference_label}:{branch_length:.6f},{consensus_label}:{branch_length:.6f});\n"
    tree_path.write_text(newick, encoding="utf-8")

    from Bio import Phylo
    from io import StringIO

    tree = Phylo.read(StringIO(newick), "newick")
    figure, axis = plt.subplots(figsize=(9, 4.5))
    Phylo.draw(tree, axes=axis, do_show=False, show_confidence=False)
    axis.set_title(f"Reference–consensus demonstration tree (p-distance {distance:.4f})")
    axis.set_xlabel("Substitutions per site")
    style_figure(figure)
    figure.savefig(figure_path, dpi=params["plot_dpi"], bbox_inches="tight")
    plt.close(figure)


def markdown_value(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def relative_link(target: Path, report_path: Path) -> str:
    return Path(os.path.relpath(target, report_path.parent)).as_posix()


def write_markdown_report(
    path: Path,
    label: str,
    inputs: dict[str, str],
    outputs: dict[str, Path],
    metrics: dict[str, Any],
    metadata: dict[str, str],
    metadata_fields: list[str],
    variants: list[dict[str, Any]],
) -> None:
    metadata_rows = [
        f"| {markdown_value(field)} | {markdown_value(metadata.get(field, ''))} |"
        for field in metadata_fields
    ]
    variant_rows = [
        f"| {variant['position']} | {variant['ref']} | {variant['alt']} | {variant['depth']} | "
        f"{variant['alt_fraction']:.4f} | {variant['change_type']} |"
        for variant in variants
    ] or ["| — | — | — | — | — | No passing variants |"]
    output_rows = [
        f"| {name} | `{markdown_value(relative_link(output_path, path))}` |"
        for name, output_path in outputs.items()
    ]
    figure_lines: list[str] = []
    for name, alt_text in (
        ("QC overview figure", "Read QC overview"),
        ("Coverage figure", "Coverage profile"),
        ("Variant figure", "Variant allele fractions"),
        ("Phylogenetic tree figure", "Phylogenetic tree"),
    ):
        if name not in outputs:
            continue
        figure_lines.extend([f"![{alt_text}]({relative_link(outputs[name], path)})", ""])
    lines = [
        "# Generic Bioinformatics Pipeline Report",
        "",
        f"- Run label: {label}",
        f"- Sample: {metrics['sample_id']}",
        f"- Reference: {metrics['reference_id']} ({metrics['reference_length']} bp)",
        f"- Reads: {metrics['passed_read_count']} / {metrics['input_read_count']} passed filters",
        f"- Q30 bases: {metrics['q30_base_percent']}%",
        f"- Reference coverage: {metrics['reference_coverage_percent']}%",
        f"- Mean retained depth: {metrics['mean_retained_depth']}×",
        f"- Passing variants: {metrics['variant_count']}",
        "",
        "## Workflow",
        "",
        "```text",
        "FASTQ + reference FASTA + metadata",
        "  -> validation and read QC",
        "  -> read filtering and demonstration alignment",
        "  -> coverage, consensus, and variant calling",
        "  -> tables, figures, metrics, and reports",
        "```",
        "",
        "## Inputs",
        "",
        *[f"- {name}: `{markdown_value(value)}`" for name, value in inputs.items()],
        "",
        "## Sample metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *metadata_rows,
        "",
        "## QC and results",
        "",
        *figure_lines,
        "## Passing variants",
        "",
        "| Position | REF | ALT | Depth | ALT fraction | Type |",
        "| ---: | --- | --- | ---: | ---: | --- |",
        *variant_rows,
        "",
        "## Output manifest",
        "",
        "| Artifact | Path |",
        "| --- | --- |",
        *output_rows,
        "",
        "## Important limitation",
        "",
        "This educational demo places every retained read at reference position 1.",
        "Its SAM and variant calls illustrate common formats but are not results from",
        "a real aligner or validated variant caller. They must not be used for biological",
        "or clinical interpretation.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html_report(
    path: Path,
    label: str,
    inputs: dict[str, str],
    outputs: dict[str, Path],
    metrics: dict[str, Any],
    metadata: dict[str, str],
    metadata_fields: list[str],
    variants: list[dict[str, Any]],
) -> None:
    escape = lambda value: html.escape(str(value), quote=True)
    metadata_rows = "".join(
        f"<tr><th>{escape(field)}</th><td>{escape(metadata.get(field, ''))}</td></tr>"
        for field in metadata_fields
    )
    variant_rows = "".join(
        "<tr>"
        f"<td>{variant['position']}</td><td>{variant['ref']}</td><td>{variant['alt']}</td>"
        f"<td>{variant['depth']}</td><td>{variant['alt_fraction']:.4f}</td>"
        f"<td>{escape(variant['change_type'])}</td>"
        "</tr>"
        for variant in variants
    ) or '<tr><td colspan="6">No variants passed filters</td></tr>'
    output_rows = "".join(
        f'<tr><th>{escape(name)}</th><td><a href="{escape(relative_link(target, path))}">'
        f"{escape(relative_link(target, path))}</a></td></tr>"
        for name, target in outputs.items()
    )
    input_rows = "".join(
        f"<tr><th>{escape(name)}</th><td><code>{escape(value)}</code></td></tr>"
        for name, value in inputs.items()
    )
    cards = [
        ("Reads passed", f"{metrics['passed_read_count']} / {metrics['input_read_count']}"),
        ("Q30 bases", f"{metrics['q30_base_percent']}%"),
        ("Reference covered", f"{metrics['reference_coverage_percent']}%"),
        ("Mean depth", f"{metrics['mean_retained_depth']}×"),
        ("Variants", metrics["variant_count"]),
    ]
    card_html = "".join(
        f'<div class="card"><span>{escape(name)}</span><strong>{escape(value)}</strong></div>'
        for name, value in cards
    )
    figure_html_parts: list[str] = []
    for name in (
        "QC overview figure",
        "Coverage figure",
        "Variant figure",
        "Phylogenetic tree figure",
    ):
        if name not in outputs:
            continue
        encoded = base64.b64encode(outputs[name].read_bytes()).decode("ascii")
        figure_html_parts.append(
            f'<figure><img src="data:image/png;base64,{encoded}" alt="{escape(name)}">'
            f"<figcaption>{escape(name)}</figcaption></figure>"
        )
    figure_html = "".join(figure_html_parts)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generic Bioinformatics Report — {escape(metrics['sample_id'])}</title>
<style>
body {{ color:#1f2933; background:#f5f7fa; font:15px/1.5 system-ui,sans-serif; margin:0; }}
main {{ max-width:1100px; margin:auto; padding:32px; }}
h1,h2 {{ color:#102a43; }} .muted {{ color:#627d98; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
.card,section {{ background:white; border:1px solid #d9e2ec; border-radius:10px; padding:18px; margin:16px 0; }}
.card span,.card strong {{ display:block; }} .card strong {{ color:#0b7285; font-size:1.5rem; }}
table {{ border-collapse:collapse; width:100%; }} th,td {{ border-bottom:1px solid #e5e7eb; padding:8px; text-align:left; }}
img {{ max-width:100%; height:auto; }} figure {{ margin:20px 0; }} figcaption {{ color:#627d98; text-align:center; }}
code {{ overflow-wrap:anywhere; }} .warning {{ border-left:5px solid #d9480f; }}
</style>
</head>
<body><main>
<h1>Generic Bioinformatics Pipeline Report</h1>
<p class="muted">Run {escape(label)} · Sample {escape(metrics['sample_id'])} · Reference {escape(metrics['reference_id'])}</p>
<div class="cards">{card_html}</div>
<section><h2>Workflow</h2><p>FASTQ + reference FASTA + metadata → validation and QC → filtering and
demonstration alignment → coverage, consensus, and variants → tables, figures, and reports.</p></section>
<section><h2>Inputs</h2><table>{input_rows}</table><h2>Sample metadata</h2><table>{metadata_rows}</table></section>
<section><h2>QC and result figures</h2>{figure_html}</section>
<section><h2>Passing variants</h2><table><thead><tr><th>Position</th><th>REF</th><th>ALT</th><th>Depth</th><th>ALT fraction</th><th>Type</th></tr></thead><tbody>{variant_rows}</tbody></table></section>
<section><h2>Output manifest</h2><table>{output_rows}</table></section>
<section class="warning"><h2>Important limitation</h2><p>This educational demo places every retained read at reference position 1.
Its SAM and variant calls are format examples, not results from a real aligner or validated caller. Do not use them for biological or clinical interpretation.</p></section>
</main></body></html>
"""
    path.write_text(document, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        fail("usage: workflow.py CONFIG.yaml")
    config_path = Path(argv[1]).expanduser().resolve()
    config = load_config(config_path)
    config_dir = config_path.parent
    raw_params = config.get("params") or {}
    if not isinstance(raw_params, dict):
        fail("config params must be a mapping")
    params = validate_params(raw_params)
    sample_id = params["sample_id"]

    input_path = configured_path(config, "input_path", config_dir)
    reference_path = configured_path(config, "reference_path", config_dir)
    metadata_path = configured_path(config, "metadata_path", config_dir)
    output_keys = [
        "report_path",
        "html_report_path",
        "metrics_path",
        "filtered_fastq_path",
        "read_qc_path",
        "sample_summary_path",
        "coverage_path",
        "alignment_sam_path",
        "consensus_fasta_path",
        "variants_vcf_path",
        "variant_table_path",
        "qc_figure_path",
        "coverage_figure_path",
        "variant_figure_path",
        "phylogenetic_tree_path",
        "phylogenetic_tree_figure_path",
    ]
    paths = {key: configured_path(config, key, config_dir) for key in output_keys}
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    records = parse_fastq(input_path)
    reference_id, reference = parse_reference(reference_path)
    metadata, metadata_fields = read_metadata(metadata_path, sample_id)
    statuses = {record.identifier: filter_reason(record, params) for record in records}
    retained = [record for record in records if statuses[record.identifier] == "pass"]
    if not retained:
        fail("no reads passed the configured filters")

    consensus, variants, positions = analyze_positions(reference, retained, params)
    depths = [position["depth"] for position in positions]
    total_bases = sum(len(record.sequence) for record in records)
    retained_bases = sum(len(record.sequence) for record in retained)
    metrics: dict[str, Any] = {
        "status": "ok",
        "pipeline": "generic_bio",
        "mode": "educational_positional_comparison",
        "sample_id": sample_id,
        "reference_id": reference_id,
        "reference_length": len(reference),
        "metadata_field_count": len(metadata_fields),
        "input_read_count": len(records),
        "passed_read_count": len(retained),
        "failed_read_count": len(records) - len(retained),
        "aligned_read_count": len(retained),
        "input_base_count": total_bases,
        "retained_base_count": retained_bases,
        "read_retention_percent": round(len(retained) / len(records) * 100, 2),
        "base_retention_percent": round(retained_bases / total_bases * 100, 2),
        "mean_input_read_length": round(statistics.fmean(len(record.sequence) for record in records), 2),
        "mean_retained_read_length": round(statistics.fmean(len(record.sequence) for record in retained), 2),
        "mean_input_quality": round(statistics.fmean(record.mean_quality for record in records), 2),
        "mean_input_gc_percent": round(statistics.fmean(record.gc_percent for record in records), 2),
        "q20_base_percent": round(quality_percent(records, 20), 2),
        "q30_base_percent": round(quality_percent(records, 30), 2),
        "mean_retained_depth": round(statistics.fmean(depths), 2),
        "maximum_retained_depth": max(depths, default=0),
        "covered_reference_bases": sum(depth > 0 for depth in depths),
        "reference_coverage_percent": round(sum(depth > 0 for depth in depths) / len(reference) * 100, 2),
        "bases_at_3x_percent": round(sum(depth >= 3 for depth in depths) / len(reference) * 100, 2),
        "variant_count": len(variants),
        "transition_count": sum(variant["change_type"] == "transition" for variant in variants),
        "transversion_count": sum(variant["change_type"] == "transversion" for variant in variants),
        "filter_outcomes": dict(sorted(Counter(statuses.values()).items())),
        "phylogenetic_tree_emitted": params["emit_phylogenetic_tree"],
        "parameters": params,
    }

    write_filtered_fastq(paths["filtered_fastq_path"], retained)
    write_read_qc(paths["read_qc_path"], records, statuses)
    write_sample_summary(paths["sample_summary_path"], metadata, metadata_fields, metrics)
    write_coverage(paths["coverage_path"], reference_id, positions)
    write_alignment_sam(
        paths["alignment_sam_path"],
        reference_id,
        reference,
        sample_id,
        metadata.get("platform", "unknown"),
        retained,
    )
    write_fasta(paths["consensus_fasta_path"], f"{sample_id}|consensus", consensus)
    write_vcf(paths["variants_vcf_path"], reference_id, len(reference), sample_id, variants)
    write_variant_table(paths["variant_table_path"], reference_id, variants)
    write_json(paths["metrics_path"], metrics)
    plot_qc(paths["qc_figure_path"], records, statuses, params)
    plot_coverage(paths["coverage_figure_path"], positions, variants, params)
    plot_variants(paths["variant_figure_path"], variants, params)
    if params["emit_phylogenetic_tree"]:
        write_phylogenetic_tree(
            paths["phylogenetic_tree_path"],
            paths["phylogenetic_tree_figure_path"],
            reference_id,
            reference,
            sample_id,
            consensus,
            params,
        )

    input_display = {
        "FASTQ reads": str(config["input_path"]),
        "Reference FASTA": str(config["reference_path"]),
        "Metadata table": str(config["metadata_path"]),
    }
    output_display = {
        "Metrics JSON": paths["metrics_path"],
        "Filtered FASTQ": paths["filtered_fastq_path"],
        "Read QC table": paths["read_qc_path"],
        "Sample summary table": paths["sample_summary_path"],
        "Coverage table": paths["coverage_path"],
        "Demonstration SAM": paths["alignment_sam_path"],
        "Consensus FASTA": paths["consensus_fasta_path"],
        "Variant VCF": paths["variants_vcf_path"],
        "Variant summary table": paths["variant_table_path"],
        "QC overview figure": paths["qc_figure_path"],
        "Coverage figure": paths["coverage_figure_path"],
        "Variant figure": paths["variant_figure_path"],
        "HTML report": paths["html_report_path"],
    }
    if params["emit_phylogenetic_tree"]:
        output_display.update(
            {
                "Phylogenetic tree": paths["phylogenetic_tree_path"],
                "Phylogenetic tree figure": paths["phylogenetic_tree_figure_path"],
            }
        )
    label = str(config.get("label") or "generic_bio")
    write_markdown_report(
        paths["report_path"],
        label,
        input_display,
        output_display,
        metrics,
        metadata,
        metadata_fields,
        variants,
    )
    output_display["Markdown report"] = paths["report_path"]
    write_html_report(
        paths["html_report_path"],
        label,
        input_display,
        output_display,
        metrics,
        metadata,
        metadata_fields,
        variants,
    )
    print(f"Generic bioinformatics pipeline completed: {paths['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
