"""Biological database search implementations."""

from __future__ import annotations

from typing import Any

from tools.infrastructure.providers.database.adapters.alphafold import query_alphafold
from tools.infrastructure.providers.database.adapters.interpro import query_interpro
from tools.infrastructure.providers.database.adapters.kegg import query_kegg
from tools.infrastructure.providers.pdb.client import query_pdb
from tools.infrastructure.providers.database.adapters.quickgo import query_quickgo
from tools.infrastructure.providers.database.adapters.uniprot import search_uniprot


def search_bio_database_tool(
    database: str,
    query: str,
    max_results: int = 5,
    operation: str | None = None,
    taxid: int | None = None,
) -> dict[str, Any]:
    clean_database = database.strip().lower()
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty.")
    if clean_database == "uniprot":
        return search_uniprot(clean_query, max_results=max_results)
    if clean_database == "interpro":
        return query_interpro(clean_query, max_results=max_results, operation=operation)
    if clean_database == "kegg":
        return query_kegg(clean_query, max_results=max_results, operation=operation)
    if clean_database == "quickgo":
        return query_quickgo(
            clean_query,
            max_results=max_results,
            operation=operation,
            taxid=taxid,
        )
    if clean_database == "pdb":
        return query_pdb(
            clean_query,
            max_results=max_results,
            operation=operation,
        )
    if clean_database == "alphafold":
        return query_alphafold(
            clean_query,
            max_results=max_results,
        )
    allowed = "alphafold, interpro, kegg, pdb, quickgo, uniprot"
    raise ValueError(f"database must be one of: {allowed}.")
