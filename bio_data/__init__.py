"""Biological data adapters."""

from .ncbi import (
    build_ncbi_args_from_text_request,
    fetch_ncbi,
    format_ncbi_result,
)
from .pdb import download_pdb_structure, search_pdb
from .uniprot import search_uniprot

__all__ = [
    "build_ncbi_args_from_text_request",
    "fetch_ncbi",
    "format_ncbi_result",
    "download_pdb_structure",
    "search_pdb",
    "search_uniprot",
]
