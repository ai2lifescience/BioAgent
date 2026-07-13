"""NCBI result formatting helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

from bio_data.ncbi_entrez.naming import _term_output_prefix
from bio_data.ncbi_entrez.spec import DEFAULT_DATE_FIELD, DEFAULT_MAX_RECORDS

def format_ncbi_result(
    result: dict[str, Any],
    fetch_args: dict[str, Any],
    target_label: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> str:
    if target_label is None:
        term = fetch_args.get("term") or ""
        target_label = _term_output_prefix(str(term), fetch_args.get("db", "nucleotide"))
    if year_start is None:
        year_start = fetch_args.get("year_start") or fetch_args.get("year")
    if year_end is None:
        year_end = fetch_args.get("year_end") or fetch_args.get("year")

    lines = [
        "NCBI retrieval completed.",
        f"Search term: {fetch_args.get('term') or fetch_args.get('terms')}",
        f"Database: {fetch_args.get('db', 'nucleotide')}",
        f"Target: {target_label}",
        f"Limit: {fetch_args.get('max_records', DEFAULT_MAX_RECORDS)} records per query",
    ]
    genes = fetch_args.get("genes")
    if genes:
        lines.append(f"Genes: {', '.join(genes)}")

    date_field = fetch_args.get("date_field", DEFAULT_DATE_FIELD)
    if year_start is not None and year_end is not None:
        if year_start == year_end:
            lines.append(
                f"Date filter: {year_start} using Entrez {date_field} "
                "(date sequence was added to GenBank for nucleotide PDAT)"
            )
        else:
            lines.append(
                f"Date filter: {year_start}-{year_end} using Entrez {date_field} "
                "(date sequence was added to GenBank for nucleotide PDAT)"
            )
    else:
        lines.append("Date filter: none")

    lines.append(f"Output directory: {fetch_args.get('output_dir') or result.get('output_dir')}")
    lines.append("")

    for item in result.get("results", []):
        label = item.get("label") or "query"
        lines.append(
            f"- {label}: matched {item.get('matched_count', 0)}, "
            f"downloaded {item.get('downloaded_count', 0)}"
        )
        if item.get("fasta_path"):
            lines.append(f"  FASTA: {item['fasta_path']}")
        if item.get("metadata_path"):
            lines.append(f"  Metadata CSV: {item['metadata_path']}")

    lines.append("")
    lines.append(
        "Metadata CSV columns include strain, date, region, country, host, subtype, "
        "and segment. The strain value matches the FASTA sequence name."
    )
    if result.get("downloaded_count", 0) == 0:
        lines.append(
            "No FASTA/CSV files were written because NCBI returned zero matching "
            f"records for this exact query. Current date: {date.today().isoformat()}."
        )
    return "\n".join(lines)
