"""Biological database search implementations."""

from __future__ import annotations

from typing import Any

from bio_data.pdb import search_pdb
from bio_data.uniprot import search_uniprot


def search_bio_database_tool(
    database: str,
    query: str,
    max_results: int = 5,
) -> dict[str, Any]:
    clean_database = database.strip().lower()
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty.")
    if clean_database == "uniprot":
        return search_uniprot(clean_query, max_results=max_results)
    if clean_database == "pdb":
        return search_pdb(clean_query, max_results=max_results)
    raise ValueError("database must be 'uniprot' or 'pdb'.")
