"""Biological data adapters."""

from .ncbi import (
    build_ncbi_args_from_text_request,
    fetch_ncbi,
    format_ncbi_result,
)
from .alphafold import query_alphafold
from .interpro import query_interpro
from .kegg import query_kegg
from .pdb import download_pdb_structure, get_pdb_entry, query_pdb, search_pdb
from .quickgo import query_quickgo
from .uniprot import search_uniprot

__all__ = [
    "build_ncbi_args_from_text_request",
    "fetch_ncbi",
    "format_ncbi_result",
    "query_alphafold",
    "query_interpro",
    "query_kegg",
    "query_quickgo",
    "query_pdb",
    "download_pdb_structure",
    "get_pdb_entry",
    "search_pdb",
    "search_uniprot",
]
