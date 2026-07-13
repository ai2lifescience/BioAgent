"""PubMed E-utilities client helpers."""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from tools.literature.constants import EUTILS_BASE_URL
from tools.literature.http import base_ncbi_params, request_get
from tools.literature.parse import parse_pubmed_article


def pubmed_search(
    term: str,
    max_records: int,
    email: str | None,
    api_key: str | None,
) -> list[str]:
    params: dict[str, Any] = {
        **base_ncbi_params(email=email, api_key=api_key),
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": max_records,
        "sort": "relevance",
    }
    response = request_get(f"{EUTILS_BASE_URL}/esearch.fcgi", params=params)
    payload = response.json()
    result = payload.get("esearchresult", {})
    if "ERROR" in result:
        raise RuntimeError(f"PubMed ESearch error: {result['ERROR']}")
    return list(result.get("idlist") or [])


def fetch_pubmed_records_by_pmids(
    pmids: list[str],
    species_name: str,
    email: str | None,
    api_key: str | None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        **base_ncbi_params(email=email, api_key=api_key),
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    response = request_get(f"{EUTILS_BASE_URL}/efetch.fcgi", params=params)
    root = ET.fromstring(response.text)
    records: list[dict[str, Any]] = []
    for article in root.findall(".//PubmedArticle"):
        record = parse_pubmed_article(article, species_name)
        if record:
            records.append(record)
    return records
