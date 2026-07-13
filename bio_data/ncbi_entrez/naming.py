"""NCBI output naming helpers."""

from __future__ import annotations

import re

from bio_data.ncbi_entrez.spec import DEFAULT_OUTPUT_DIR_PREFIX, DEFAULT_OUTPUT_DIR_TEMPLATE

def _slugify(text: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower()).strip("-")
    return (slug or "ncbi")[:max_length].strip("-") or "ncbi"

def _safe_name(text: str, max_length: int = 80) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip()).strip("._-")
    return (name or "ncbi")[:max_length].strip("._-") or "ncbi"

def _looks_like_phix174(term: str) -> bool:
    return "phix174" in re.sub(r"[^a-z0-9]+", "", term.lower())

def _term_output_prefix(term: str, db: str) -> str:
    if _looks_like_phix174(term):
        return "phix174"
    organism_match = re.search(r'"([^"]+)"\s*\[Organism\]', term, flags=re.IGNORECASE)
    if organism_match:
        return _safe_name(organism_match.group(1).lower())
    unquoted_organism_match = re.search(
        r"([A-Za-z][A-Za-z0-9._ -]+?)\s*\[Organism\]",
        term,
        flags=re.IGNORECASE,
    )
    if unquoted_organism_match:
        return _safe_name(unquoted_organism_match.group(1).strip().lower())
    return f"{_slugify(db)}_{_slugify(term, max_length=40)}"

def _query_output_stem(term: str, db: str, timestamp: str, label: str | None) -> str:
    if label:
        clean_label = _safe_name(label)
        return f"{_term_output_prefix(term, db)}_{clean_label}"
    return f"{_slugify(db)}_{_slugify(term)}_{timestamp}"

def _request_output_dir(target_label: str, year_start: int | None, year_end: int | None) -> str:
    base = _safe_name(target_label.lower())
    output_dir = f"{DEFAULT_OUTPUT_DIR_PREFIX}_{base}"
    if year_start is None or year_end is None:
        return output_dir
    if year_start == year_end:
        return f"{output_dir}_{year_start}"
    return f"{output_dir}_{year_start}_{year_end}"

def _default_output_label(
    term: str | None,
    terms: list[str] | None,
    accessions: list[str] | None,
    db: str,
) -> str:
    if term:
        return _term_output_prefix(term, db)
    if terms:
        if len(terms) == 1:
            return _term_output_prefix(terms[0], db)
        return "multi"
    if accessions:
        return "accessions"
    return "ncbi"

def _resolve_output_dir(
    output_dir: str | None,
    target_label: str,
    year_range: tuple[int, int] | None,
) -> str:
    if output_dir and output_dir not in {DEFAULT_OUTPUT_DIR_PREFIX, DEFAULT_OUTPUT_DIR_TEMPLATE}:
        return output_dir

    year_start: int | None = None
    year_end: int | None = None
    if year_range is not None:
        year_start, year_end = year_range
    return _request_output_dir(target_label, year_start, year_end)
