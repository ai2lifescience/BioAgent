"""InterPro REST API adapter."""

from __future__ import annotations

import re
from typing import Any

from bio_data.api_http import request_api, response_provenance


INTERPRO_BASE_URL = "https://www.ebi.ac.uk/interpro/api"
INTERPRO_ACCESSION = re.compile(r"^IPR\d{6}$", re.IGNORECASE)
PROTEIN_ACCESSION = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$",
    re.IGNORECASE,
)


def query_interpro(
    query: str,
    max_results: int = 5,
    operation: str | None = None,
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("InterPro query must not be empty.")
    limit = max(1, min(int(max_results), 100))
    clean_operation = (operation or "").strip().lower().replace("-", "_")

    if clean_operation in {"entry", "entry_details"} or INTERPRO_ACCESSION.fullmatch(clean_query):
        if not INTERPRO_ACCESSION.fullmatch(clean_query):
            raise ValueError("InterPro entry identifiers must look like IPR000001.")
        accession = clean_query.upper()
        url = f"{INTERPRO_BASE_URL}/entry/interpro/{accession.lower()}/"
        params = None
        operation_name = "entry_details"
    elif clean_operation in {"protein", "protein_domains", "domains"} or PROTEIN_ACCESSION.fullmatch(clean_query):
        if not PROTEIN_ACCESSION.fullmatch(clean_query):
            raise ValueError("InterPro protein lookup requires a UniProt-style accession.")
        accession = clean_query.upper()
        url = f"{INTERPRO_BASE_URL}/entry/interpro/protein/uniprot/{accession.lower()}/"
        params = {"page_size": limit}
        operation_name = "protein_domains"
    else:
        url = f"{INTERPRO_BASE_URL}/entry/interpro/"
        params = {"search": clean_query, "page_size": limit}
        operation_name = "entry_search"

    payload = request_api("GET", url, params=params).json()
    raw_results = payload.get("results", []) if isinstance(payload, dict) else []
    if isinstance(payload, dict) and not raw_results and payload.get("metadata"):
        raw_results = [payload]
    records = [_normalize_interpro_record(item) for item in raw_results[:limit] if isinstance(item, dict)]
    return {
        "database": "interpro",
        "query": clean_query,
        "operation": operation_name,
        "record_count": len(records),
        "records": records,
        "provenance": response_provenance(url, operation_name),
        "warnings": [],
    }


def _normalize_interpro_record(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else item
    source = metadata.get("source_database")
    if isinstance(source, dict):
        source = source.get("name") or source.get("code")
    record = {
        "accession": metadata.get("accession") or metadata.get("integrated"),
        "name": metadata.get("name") or metadata.get("short_name"),
        "type": metadata.get("type"),
        "source_database": source or "interpro",
        "description": metadata.get("description"),
        "go_terms": _extract_go_terms(metadata),
    }
    proteins = item.get("proteins")
    if isinstance(proteins, list):
        record["protein_count"] = len(proteins)
    locations = item.get("entry_protein_locations")
    if isinstance(locations, list):
        record["locations"] = locations
    return {key: value for key, value in record.items() if value not in (None, "", [])}


def _extract_go_terms(metadata: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    raw_terms = metadata.get("go_terms") or metadata.get("goTerms") or []
    if isinstance(raw_terms, list):
        for term in raw_terms:
            if isinstance(term, str):
                terms.append(term)
            elif isinstance(term, dict):
                identifier = term.get("identifier") or term.get("id")
                if identifier:
                    terms.append(str(identifier))
    return terms
