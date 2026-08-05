"""Strict, configurable MEGARes metadata loading."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Mapping

from .errors import ParseError


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "accession": (
        "accession", "accession_number", "sequence_accession", "megares_accession",
        "header", "id",
    ),
    "gene": ("gene", "gene_name", "resistance_gene", "name"),
    "product": ("product", "description", "annotation"),
    "compound_type": ("compound_type", "type", "drug_type", "compound"),
    "class": ("class", "drug_class", "antimicrobial_class"),
    "mechanism": ("mechanism", "resistance_mechanism"),
    "group": ("group", "gene_group", "resistance_group"),
    "resistance": ("resistance", "phenotype", "drug", "antibiotic"),
    "requires_snp_confirmation": (
        "requires_snp_confirmation", "snp_confirmation_required", "requires_snp",
    ),
}
OUTPUT_FIELDS = tuple(FIELD_ALIASES)


def normalize_header(value: str) -> str:
    """Normalize only header punctuation/case, not semantic content."""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def normalize_accession(value: str) -> str:
    """Normalize an accession for exact metadata joins."""
    cleaned = value.strip().lstrip(">").split()[0] if value.strip() else ""
    if "|" in cleaned:
        tokens = [token for token in cleaned.split("|") if token]
        if len(tokens) >= 2 and tokens[0].lower() in {"gb", "emb", "dbj", "ref"}:
            cleaned = tokens[1]
    cleaned = re.sub(r"\.\d+$", "", cleaned)
    return cleaned.upper()


def _dialect(path: Path, sample: str) -> csv.Dialect:
    if path.suffix.lower() == ".csv":
        return csv.excel
    if path.suffix.lower() in {".tsv", ".tab"}:
        return csv.excel_tab
    try:
        return csv.Sniffer().sniff(sample, delimiters="\t,")
    except csv.Error:
        return csv.excel_tab


def _resolve_fields(
    headers: list[str], configured: Mapping[str, Any] | None
) -> dict[str, str | None]:
    normalized = {normalize_header(header): header for header in headers}
    mapping: dict[str, str | None] = {}
    configured = configured or {}
    for logical, aliases in FIELD_ALIASES.items():
        requested = configured.get(logical)
        if requested:
            key = normalize_header(str(requested))
            if key not in normalized:
                raise ParseError(
                    f"Configured MEGARes metadata field '{requested}' for '{logical}' "
                    "does not exist."
                )
            mapping[logical] = normalized[key]
            continue
        candidates = [normalized[alias] for alias in aliases if alias in normalized]
        if len(candidates) > 1:
            raise ParseError(
                f"Ambiguous MEGARes metadata fields for '{logical}': {candidates}. "
                "Set metadata_fields explicitly."
            )
        mapping[logical] = candidates[0] if candidates else None
    if mapping["accession"] is None:
        raise ParseError(
            "MEGARes metadata is missing an accession join field. "
            "Configure metadata_fields.accession."
        )
    return mapping


def load_metadata(
    path: Path, configured_fields: Mapping[str, Any] | None = None
) -> dict[str, dict[str, str]]:
    """Load MEGARes TSV/CSV keyed by normalized accession."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ParseError(f"Cannot read MEGARes metadata: {path}") from exc
    if not text.strip():
        raise ParseError(f"MEGARes metadata is empty: {path}")
    dialect = _dialect(path, text[:4096])
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    if not reader.fieldnames:
        raise ParseError(f"MEGARes metadata has no header: {path}")
    fields = _resolve_fields([name.strip() for name in reader.fieldnames], configured_fields)
    result: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(reader, start=2):
        raw_accession = str(row.get(fields["accession"] or "", "") or "")
        accession = normalize_accession(raw_accession)
        if not accession:
            raise ParseError(f"MEGARes metadata row {line_number} has an empty accession.")
        if accession in result:
            raise ParseError(f"Duplicate normalized MEGARes accession: {accession}")
        result[accession] = {
            logical: str(row.get(source, "") or "").strip() if source else ""
            for logical, source in fields.items()
        }
        result[accession]["accession"] = raw_accession.strip()
    return result


def truthy(value: str) -> bool:
    """Interpret explicit metadata boolean values."""
    return value.strip().lower() in {"1", "true", "yes", "y", "required"}
