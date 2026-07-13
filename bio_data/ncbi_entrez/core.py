"""NCBI Entrez retrieval facade.

Detailed implementation lives in focused modules:
``spec.py``, ``naming.py``, ``filters.py``, ``query.py``, ``http.py``,
``metadata.py``, ``download.py``, ``request_parser.py``, and ``format.py``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from bio_data.ncbi_entrez.download import _download_one_query
from bio_data.ncbi_entrez.filters import _resolve_year_range
from bio_data.ncbi_entrez.format import format_ncbi_result
from bio_data.ncbi_entrez.naming import _default_output_label, _resolve_output_dir
from bio_data.ncbi_entrez.query import _build_default_query_if_needed, _build_queries
from bio_data.ncbi_entrez.request_parser import build_ncbi_args_from_text_request
from bio_data.ncbi_entrez.spec import DEFAULT_DATE_FIELD, DEFAULT_MAX_RECORDS


def fetch_ncbi(
    term: str | None = None,
    db: str = "nucleotide",
    max_records: int = DEFAULT_MAX_RECORDS,
    year: int | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    date_field: str = DEFAULT_DATE_FIELD,
    output_dir: str | None = None,
    filename: str | None = None,
    metadata_filename: str | None = None,
    terms: list[str] | None = None,
    genes: list[str] | None = None,
    accessions: list[str] | None = None,
    email: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Download one or more NCBI FASTA sequence sets plus CSV metadata."""
    if max_records < 1:
        raise ValueError("max_records must be at least 1.")

    clean_db = db.strip().lower()
    clean_date_field = date_field.strip().upper()
    if clean_date_field not in {"PDAT", "MDAT"}:
        raise ValueError("date_field must be PDAT or MDAT.")
    year_range = _resolve_year_range(
        year=year,
        year_start=year_start,
        year_end=year_end,
    )
    effective_term, effective_genes = _build_default_query_if_needed(
        term=term,
        genes=genes,
        terms=terms,
        accessions=accessions,
    )
    queries = _build_queries(
        term=effective_term,
        terms=terms,
        genes=effective_genes,
        accessions=accessions,
        year_range=year_range,
        date_field=clean_date_field,
    )
    output_label = _default_output_label(effective_term, terms, accessions, clean_db)
    clean_output_dir = _resolve_output_dir(output_dir, output_label, year_range)
    output_root = Path(clean_output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    is_batch = len(queries) > 1

    results = []
    for query in queries:
        result = _download_one_query(
            term=str(query["term"]),
            db=clean_db,
            max_records=max_records,
            output_root=output_root,
            timestamp=timestamp,
            label=query.get("label"),
            filename=None if is_batch else filename,
            metadata_filename=None if is_batch else metadata_filename,
            email=email,
            api_key=api_key,
        )
        if query.get("label"):
            result["label"] = query["label"]
        results.append(result)

    downloaded_count = sum(result["downloaded_count"] for result in results)
    matched_count = sum(result["matched_count"] for result in results)

    return {
        "db": clean_db,
        "sequence_format": "fasta",
        "metadata_format": "csv",
        "query_count": len(results),
        "matched_count": matched_count,
        "downloaded_count": downloaded_count,
        "output_dir": str(output_root),
        "results": results,
        "fasta_paths": [result["fasta_path"] for result in results if result.get("fasta_path")],
        "metadata_paths": [
            result["metadata_path"] for result in results if result.get("metadata_path")
        ],
    }


__all__ = [
    "build_ncbi_args_from_text_request",
    "fetch_ncbi",
    "format_ncbi_result",
]
