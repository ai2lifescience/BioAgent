"""NCBI Entrez adapter implementation owned by the ncbi_retrieval function tool."""

from .service import build_ncbi_args_from_text_request, fetch_ncbi, format_ncbi_result

__all__ = ["build_ncbi_args_from_text_request", "fetch_ncbi", "format_ncbi_result"]
