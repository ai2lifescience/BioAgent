"""PubMed collection facade."""

from __future__ import annotations

from typing import Any

from tools.literature.client import fetch_pubmed_records_by_pmids, pubmed_search
from tools.literature.query import pubmed_query


def collect_pubmed_records(
    species_name: str,
    question: str,
    max_records: int = 6,
    email: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    focused_query, fallback_query = pubmed_query(species_name, question)
    pmids = pubmed_search(
        focused_query,
        max_records=max_records,
        email=email,
        api_key=api_key,
    )
    used_query = focused_query
    if not pmids and fallback_query != focused_query:
        pmids = pubmed_search(
            fallback_query,
            max_records=max_records,
            email=email,
            api_key=api_key,
        )
        used_query = fallback_query
    if not pmids:
        return {
            "status": "ok",
            "species_name": species_name,
            "query": used_query,
            "pmids": [],
            "record_count": 0,
            "records": [],
        }

    records = fetch_pubmed_records_by_pmids(
        pmids=pmids,
        species_name=species_name,
        email=email,
        api_key=api_key,
    )
    return {
        "status": "ok",
        "species_name": species_name,
        "query": used_query,
        "pmids": pmids,
        "record_count": len(records),
        "records": records,
    }
