"""QuickGO REST API adapter."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from bio_data.api_http import request_api, response_provenance


QUICKGO_BASE_URL = "https://www.ebi.ac.uk/QuickGO/services"
GO_ID = re.compile(r"^GO:\d{7}$", re.IGNORECASE)
ALLOWED_OPERATIONS = {"term_search", "term_details", "annotation_search", "gene_product_search"}


def query_quickgo(
    query: str,
    max_results: int = 25,
    operation: str | None = None,
    taxid: int | None = None,
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("QuickGO query must not be empty.")
    limit = max(1, min(int(max_results), 100))
    if taxid is not None and not 1 <= int(taxid) <= 2_147_483_647:
        raise ValueError("QuickGO taxid must be a positive integer.")
    clean_operation = (operation or "").strip().lower().replace("-", "_")
    if not clean_operation:
        clean_operation = "term_details" if GO_ID.fullmatch(clean_query) else "term_search"
    if clean_operation not in ALLOWED_OPERATIONS:
        allowed = ", ".join(sorted(ALLOWED_OPERATIONS))
        raise ValueError(f"QuickGO operation must be one of: {allowed}.")

    params: dict[str, Any] | None
    if clean_operation == "term_details":
        if not GO_ID.fullmatch(clean_query):
            raise ValueError("QuickGO term details require an identifier such as GO:0008150.")
        url = f"{QUICKGO_BASE_URL}/ontology/go/terms/{quote(clean_query.upper(), safe=':')}"
        params = None
    elif clean_operation == "annotation_search":
        url = f"{QUICKGO_BASE_URL}/annotation/search"
        params = {"geneProductId": clean_query, "limit": limit}
        if taxid is not None:
            params["taxonId"] = int(taxid)
    elif clean_operation == "gene_product_search":
        url = f"{QUICKGO_BASE_URL}/geneproduct/search"
        params = {"query": clean_query, "limit": limit}
        if taxid is not None:
            params["taxonId"] = int(taxid)
    else:
        url = f"{QUICKGO_BASE_URL}/ontology/go/search"
        params = {"query": clean_query, "limit": limit}

    payload = request_api("GET", url, params=params).json()
    raw_results = payload.get("results", []) if isinstance(payload, dict) else []
    records = [_normalize_quickgo_record(item) for item in raw_results[:limit] if isinstance(item, dict)]
    return {
        "database": "quickgo",
        "query": clean_query,
        "operation": clean_operation,
        "record_count": len(records),
        "records": records,
        "provenance": response_provenance(url, clean_operation),
        "warnings": [],
    }


def _normalize_quickgo_record(item: dict[str, Any]) -> dict[str, Any]:
    definition = item.get("definition")
    if isinstance(definition, dict):
        definition = definition.get("text")
    record = {
        "id": item.get("id") or item.get("goId") or item.get("geneProductId"),
        "name": item.get("name") or item.get("goName") or item.get("symbol"),
        "definition": definition,
        "aspect": item.get("aspect"),
        "gene_product_id": item.get("geneProductId"),
        "go_id": item.get("goId"),
        "taxid": item.get("taxonId"),
        "evidence_code": item.get("evidenceCode"),
        "qualifier": item.get("qualifier"),
        "reference": item.get("reference"),
    }
    return {key: value for key, value in record.items() if value not in (None, "", [])}
