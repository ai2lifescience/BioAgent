"""Strict, configurable VFDB core metadata loading."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Mapping

from .errors import ParseError


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "accession": (
        "accession", "accession_number", "sequence_accession", "nucleotide_accession",
        "genbank_accession", "id",
    ),
    "vf_id": ("vf_id", "vfid", "vf_identifier", "virulence_factor_id"),
    "gene": ("gene", "gene_name", "symbol"),
    "factor_name": (
        "factor_name", "vf_name", "virulence_factor", "factor", "name",
    ),
    "category": ("category", "vf_category", "major_category"),
    "subcategory": ("subcategory", "sub_category", "vf_subcategory"),
    "associated_pathogen": (
        "associated_pathogen", "pathogen", "organism", "species",
    ),
    "product": ("product", "description", "annotation"),
}
OUTPUT_FIELDS = tuple(FIELD_ALIASES)


def normalize_header(value: str) -> str:
    """Normalize header punctuation and case."""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def normalize_accession(value: str) -> str:
    """Normalize an accession for strict equality joins."""
    cleaned = value.strip().lstrip(">").split()[0] if value.strip() else ""
    if "|" in cleaned:
        tokens = [token for token in cleaned.split("|") if token]
        if len(tokens) >= 2 and tokens[0].lower() in {"gb", "emb", "dbj", "ref"}:
            cleaned = tokens[1]
    return re.sub(r"\.\d+$", "", cleaned).upper()


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
    configured = configured or {}
    result: dict[str, str | None] = {}
    for logical, aliases in FIELD_ALIASES.items():
        requested = configured.get(logical)
        if requested:
            key = normalize_header(str(requested))
            if key not in normalized:
                raise ParseError(
                    f"Configured VFDB metadata field '{requested}' for '{logical}' does not exist."
                )
            result[logical] = normalized[key]
            continue
        candidates = [normalized[alias] for alias in aliases if alias in normalized]
        if len(candidates) > 1:
            raise ParseError(
                f"Ambiguous VFDB metadata fields for '{logical}': {candidates}. "
                "Set metadata_fields explicitly."
            )
        result[logical] = candidates[0] if candidates else None
    if result["accession"] is None:
        raise ParseError(
            "VFDB metadata is missing an accession join field. "
            "Configure metadata_fields.accession."
        )
    return result


def load_metadata(
    path: Path, configured_fields: Mapping[str, Any] | None = None
) -> dict[str, dict[str, str]]:
    """Load VFDB CSV/TSV keyed by normalized accession."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ParseError(f"Cannot read VFDB metadata: {path}") from exc
    if not text.strip():
        raise ParseError(f"VFDB metadata is empty: {path}")
    reader = csv.DictReader(text.splitlines(), dialect=_dialect(path, text[:4096]))
    if not reader.fieldnames:
        raise ParseError(f"VFDB metadata has no header: {path}")
    fields = _resolve_fields([name.strip() for name in reader.fieldnames], configured_fields)
    result: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(reader, start=2):
        raw_accession = str(row.get(fields["accession"] or "", "") or "")
        accession = normalize_accession(raw_accession)
        if not accession:
            raise ParseError(f"VFDB metadata row {line_number} has an empty accession.")
        if accession in result:
            raise ParseError(f"Duplicate normalized VFDB accession: {accession}")
        result[accession] = {
            logical: str(row.get(source, "") or "").strip() if source else ""
            for logical, source in fields.items()
        }
        result[accession]["accession"] = raw_accession.strip()
    return result
