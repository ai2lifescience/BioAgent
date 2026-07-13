"""NCBI data adapter."""

from bio_data.ncbi_entrez import (
    build_ncbi_args_from_text_request,
    fetch_ncbi,
    format_ncbi_result,
)

__all__ = [
    "build_ncbi_args_from_text_request",
    "fetch_ncbi",
    "format_ncbi_result",
]
