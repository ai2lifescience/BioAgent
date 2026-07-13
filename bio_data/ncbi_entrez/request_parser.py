"""Parse simple natural-language NCBI requests."""

from __future__ import annotations

import re
from typing import Any

from bio_data.ncbi_entrez.naming import _request_output_dir, _term_output_prefix
from bio_data.ncbi_entrez.spec import DEFAULT_MAX_RECORDS, PHIX174_SEARCH_TERM

def _unique_preserving_case(items: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        value = item.strip()
        key = value.upper()
        if value and key not in seen:
            seen.add(key)
            values.append(value.upper() if len(value) == 1 else value)
    return values

def _parse_record_limit(request: str) -> int:
    match = re.search(r"\b(\d+)\s*(?:records?|recods?)\b", request, flags=re.IGNORECASE)
    if not match:
        return DEFAULT_MAX_RECORDS
    return max(1, int(match.group(1)))

def _parse_request_years(request: str) -> tuple[int | None, int | None]:
    range_match = re.search(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})\b", request)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", request)]
    if years:
        return years[0], years[0]
    return None, None

def _parse_request_db(request: str) -> str:
    db_match = re.search(r"\bdb\s*[:=]\s*([A-Za-z_]+)\b", request, flags=re.IGNORECASE)
    if db_match:
        return db_match.group(1).lower()
    if re.search(r"\bprotein\b", request, flags=re.IGNORECASE):
        return "protein"
    return "nucleotide"

def _strip_outer_quotes(value: str) -> str:
    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {"'", '"'}:
        return clean[1:-1].strip()
    return clean

def _as_organism_term(value: str) -> str:
    clean = _strip_outer_quotes(value)
    if "[" in clean and "]" in clean:
        return clean
    return f'"{clean}"[Organism]'

def _find_quoted_argument(request: str, names: tuple[str, ...]) -> tuple[str, int] | None:
    joined = "|".join(re.escape(name) for name in names)
    pattern = rf"\b(?:{joined})\b\s*(?::|=)?\s*(['\"])(.+?)\1"
    match = re.search(pattern, request, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(2).strip(), match.end()

def _parse_request_term(request: str) -> tuple[str, str, int] | None:
    explicit_query = _find_quoted_argument(request, ("query", "term"))
    if explicit_query:
        term, end = explicit_query
        return term, _term_output_prefix(term, "nucleotide"), end

    explicit_organism = _find_quoted_argument(request, ("organism", "phage"))
    if explicit_organism:
        organism, end = explicit_organism
        term = _as_organism_term(organism)
        return term, _term_output_prefix(term, "nucleotide"), end

    if re.search(r"phi\s*x\s*174|phix174", request, flags=re.IGNORECASE):
        match = re.search(r"phi\s*x\s*174|phix174", request, flags=re.IGNORECASE)
        assert match is not None
        return PHIX174_SEARCH_TERM, "phix174", match.end()

    organism_phrase = re.search(
        r"\b([A-Z][A-Za-z0-9._-]*(?:\s+[a-z][A-Za-z0-9._-]*){0,3}\s+phage\s+(?!genes?\b)[A-Za-z0-9._-]+)\b",
        request,
    )
    if organism_phrase:
        organism = organism_phrase.group(1)
        term = _as_organism_term(organism)
        return term, _term_output_prefix(term, "nucleotide"), organism_phrase.end()

    short_phage = re.search(r"\b([A-Za-z0-9._-]+)\s+phage\b", request, flags=re.IGNORECASE)
    if short_phage:
        organism = f"{short_phage.group(1)} phage"
        term = _as_organism_term(organism)
        return term, _term_output_prefix(term, "nucleotide"), short_phage.end()

    return None

def _parse_request_genes(request: str, target_end: int) -> list[str] | None:
    marker = re.search(r"\bgenes?\b\s*(?::|=)?\s*", request, flags=re.IGNORECASE)
    if marker:
        segment = request[marker.end() :]
    else:
        segment = request[target_end:]

    segment = re.split(r"\b(?:19|20)\d{2}\b", segment, maxsplit=1)[0]
    segment = re.split(
        r"\b(?:records?|recods?|sequences?|from|between|during|year|years|using|with|db|database|metadata)\b",
        segment,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    raw_tokens = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9*_.-]*\b", segment)
    stopwords = {
        "and",
        "or",
        "of",
        "the",
        "for",
        "gene",
        "genes",
        "phage",
        "organism",
        "query",
        "term",
        "download",
        "fetch",
        "retrieve",
        "search",
    }
    genes = [token for token in raw_tokens if token.lower() not in stopwords]
    return _unique_preserving_case(genes) or None

def build_ncbi_args_from_text_request(user_request: str) -> dict[str, Any] | None:
    """Parse simple NCBI download requests into fetch_ncbi keyword arguments."""
    if not re.search(r"\b(download|fetch|retrieve|search)\b", user_request, re.IGNORECASE):
        return None

    target = _parse_request_term(user_request)
    if target is None:
        return None
    term, target_label, target_end = target

    max_records = _parse_record_limit(user_request)
    year_start, year_end = _parse_request_years(user_request)
    db = _parse_request_db(user_request)
    genes = _parse_request_genes(user_request, target_end)
    output_dir = _request_output_dir(target_label, year_start, year_end)

    fetch_args: dict[str, Any] = {
        "term": term,
        "db": db,
        "max_records": max_records,
        "output_dir": output_dir,
    }
    if genes:
        fetch_args["genes"] = genes
    if year_start is not None and year_end is not None:
        fetch_args["year_start"] = year_start
        fetch_args["year_end"] = year_end
    return fetch_args
