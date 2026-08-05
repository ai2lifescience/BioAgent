"""ABRicate command construction and name-based result parsing."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping

from .command import CommandRunner
from .config import PipelineConfig
from .errors import ParseError
from .metadata import normalize_accession, truthy


ARG_FIELDS = [
    "sample_id", "contig", "start", "end", "strand", "gene", "accession",
    "product", "compound_type", "class", "mechanism", "group", "resistance",
    "pct_identity", "pct_coverage", "coverage", "gaps", "supporting_reads", "depth",
    "database_name",
    "database_version", "locus_tag", "prokka_gene", "prokka_product",
    "requires_snp_confirmation", "snp_status", "final_call",
]


def abricate_command(
    assembly: Path, config: PipelineConfig
) -> list[str]:
    """Build the configured custom-MEGARes ABRicate command."""
    tool = config.value("tools", "abricate")
    datadir = config.database_path("abricate_datadir")
    return [
        str(tool["executable"]),
        *[str(item) for item in tool.get("prefix_options", [])],
        "--datadir", str(datadir),
        "--db", str(tool["database_name"]),
        "--minid", str(tool["min_identity"]),
        "--mincov", str(tool["min_coverage"]),
        "--threads", str(config.threads),
        str(assembly),
    ]


def run_abricate(
    assembly: Path, raw_path: Path, config: PipelineConfig, runner: CommandRunner
) -> Path:
    """Stream ABRicate stdout directly to its raw TSV."""
    runner.run(
        abricate_command(assembly, config),
        tool="ABRicate",
        log_path=raw_path.parent.parent / "logs" / "abricate.log",
        stdout_path=raw_path,
    )
    return raw_path


def _canon(value: str) -> str:
    return value.lstrip("#").strip().upper().replace(" ", "_")


def _get(row: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = row.get(_canon(name), "")
        if value not in ("", "."):
            return value.strip()
    return ""


def _integer(value: str, field: str, line_number: int) -> int:
    try:
        return int(float(value))
    except ValueError as exc:
        raise ParseError(f"ABRicate line {line_number} has invalid {field}: {value}") from exc


def parse_abricate(path: Path) -> list[dict[str, Any]]:
    """Parse ABRicate using header names and preserve empty-hit success."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            lines = [line for line in handle if line.strip()]
    except OSError as exc:
        raise ParseError(f"Cannot read ABRicate output: {path}") from exc
    if not lines:
        raise ParseError(f"ABRicate output is empty and has no header: {path}")
    reader = csv.DictReader(lines, delimiter="\t")
    if not reader.fieldnames:
        raise ParseError(f"ABRicate output has no header: {path}")
    reader.fieldnames = [_canon(name) for name in reader.fieldnames]
    required = {"SEQUENCE", "START", "END", "GENE"}
    if not required.issubset(set(reader.fieldnames)):
        missing = sorted(required - set(reader.fieldnames))
        raise ParseError(f"ABRicate output is missing required columns: {missing}")
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(reader, start=2):
        row = {_canon(key): str(value or "") for key, value in raw.items()}
        start = _integer(_get(row, "START"), "START", line_number)
        end = _integer(_get(row, "END"), "END", line_number)
        strand = _get(row, "STRAND") or ("-" if start > end else "+")
        rows.append(
            {
                "contig": _get(row, "SEQUENCE"),
                "start": min(start, end),
                "end": max(start, end),
                "strand": strand,
                "gene": _get(row, "GENE"),
                "accession": _get(row, "ACCESSION"),
                "product": _get(row, "PRODUCT"),
                "resistance": _get(row, "RESISTANCE"),
                "pct_identity": _get(row, "%IDENTITY", "IDENTITY"),
                "pct_coverage": _get(row, "%COVERAGE"),
                "coverage": _get(row, "COVERAGE"),
                "gaps": _get(row, "GAPS"),
            }
        )
    return rows


def enrich_hits(
    hits: Iterable[Mapping[str, Any]],
    metadata: Mapping[str, Mapping[str, str]],
    sample_id: str,
    database_name: str,
    database_version: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Join hierarchy and conservative SNP-call semantics onto hits."""
    enriched: list[dict[str, Any]] = []
    for hit in hits:
        raw_accession = str(hit.get("accession", ""))
        accession = normalize_accession(raw_accession)
        meta = metadata.get(accession)
        if meta is None:
            warnings.append(
                f"ABRicate hit accession '{raw_accession or '(empty)'}' "
                "did not match MEGARes metadata."
            )
            meta = {}
        requires_snp = truthy(str(meta.get("requires_snp_confirmation", "")))
        row = {field: "" for field in ARG_FIELDS}
        row.update(hit)
        row.update(
            {
                "sample_id": sample_id,
                "accession": raw_accession if raw_accession != "." else "",
                "compound_type": meta.get("compound_type", ""),
                "class": meta.get("class", ""),
                "mechanism": meta.get("mechanism", ""),
                "group": meta.get("group", ""),
                "resistance": hit.get("resistance") or meta.get("resistance", ""),
                "product": hit.get("product") or meta.get("product", ""),
                "database_name": database_name,
                "database_version": database_version,
                "requires_snp_confirmation": str(requires_snp).lower(),
                "snp_status": "not_evaluated",
                "final_call": "candidate_hit" if requires_snp else "sequence_homology_hit",
            }
        )
        enriched.append(row)
    return sorted(
        enriched,
        key=lambda row: (
            str(row["contig"]), str(row["start"]).zfill(20),
            str(row["end"]).zfill(20), str(row["gene"])
        ),
    )
