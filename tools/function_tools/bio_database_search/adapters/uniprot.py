"""UniProt REST API adapter."""

from __future__ import annotations

from typing import Any

import requests


UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
REQUEST_TIMEOUT = 30


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    if isinstance(value, dict):
        for key in ("fullName", "shortName", "value"):
            text = _first_text(value.get(key))
            if text:
                return text
    if isinstance(value, str):
        return value
    return ""


def search_uniprot(query: str, max_results: int = 5) -> dict[str, Any]:
    params = {
        "query": query,
        "format": "json",
        "size": max(1, min(max_results, 25)),
        "fields": "accession,id,protein_name,organism_name,gene_names,reviewed",
    }
    response = requests.get(UNIPROT_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    records = []
    for item in payload.get("results", []):
        accession = item.get("primaryAccession", "")
        protein = item.get("proteinDescription", {}).get("recommendedName", {})
        records.append(
            {
                "accession": accession,
                "id": item.get("uniProtkbId", ""),
                "name": _first_text(protein) or item.get("uniProtkbId", ""),
                "organism": item.get("organism", {}).get("scientificName", ""),
                "genes": [
                    gene.get("geneName", {}).get("value", "")
                    for gene in item.get("genes", [])
                    if gene.get("geneName", {}).get("value")
                ],
                "reviewed": item.get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
                "url": f"https://www.uniprot.org/uniprotkb/{accession}/entry" if accession else "",
            }
        )

    return {
        "database": "uniprot",
        "query": query,
        "record_count": len(records),
        "records": records,
    }
