"""NCBI FASTA and metadata download workflow helpers."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from bio_data.ncbi_entrez.http import _base_params, _request_get, _search_ncbi
from bio_data.ncbi_entrez.metadata import _download_metadata_from_history
from bio_data.ncbi_entrez.naming import _query_output_stem, _term_output_prefix
from bio_data.ncbi_entrez.spec import DEFAULT_BATCH_SIZE

def _download_from_history(
    db: str,
    query_key: str,
    webenv: str,
    download_count: int,
    output_path: Path,
    email: str | None,
    api_key: str | None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    with output_path.open("wb") as output_handle:
        for retstart in range(0, download_count, batch_size):
            retmax = min(batch_size, download_count - retstart)
            params: dict[str, Any] = {
                **_base_params(email=email, api_key=api_key),
                "db": db,
                "query_key": query_key,
                "WebEnv": webenv,
                "retstart": retstart,
                "retmax": retmax,
                "rettype": "fasta",
                "retmode": "text",
            }
            response = _request_get("efetch.fcgi", params, stream=True)
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    output_handle.write(chunk)
            if retstart + retmax < download_count:
                time.sleep(0.34)

def _normalize_fasta_headers(output_path: Path, sequence_names: list[str] | None = None) -> int:
    """Rewrite FASTA sequence names and return record count."""
    text = output_path.read_text(encoding="utf-8")
    record_count = 0
    normalized_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            record_count += 1
            header = line[1:].strip()
            if sequence_names and record_count <= len(sequence_names):
                sequence_name = sequence_names[record_count - 1]
            else:
                sequence_name = header.split()[0] if header else f"sequence_{record_count}"
            normalized_lines.append(f">{sequence_name}")
        else:
            normalized_lines.append(line)
    output_path.write_text("\n".join(normalized_lines) + "\n", encoding="utf-8")
    return record_count

def _download_one_query(
    term: str,
    db: str,
    max_records: int,
    output_root: Path,
    timestamp: str,
    label: str | None = None,
    filename: str | None = None,
    metadata_filename: str | None = None,
    email: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    clean_term = term.strip()
    subtype = _term_output_prefix(clean_term, db)
    output_stem = _query_output_stem(clean_term, db, timestamp, label)
    query_output_root = output_root
    query_output_root.mkdir(parents=True, exist_ok=True)

    search = _search_ncbi(
        term=clean_term,
        db=db,
        max_records=max_records,
        email=email,
        api_key=api_key,
    )
    if search["download_count"] == 0:
        return {
            "term": clean_term,
            "db": db,
            "sequence_format": "fasta",
            "metadata_format": "csv",
            "matched_count": search["count"],
            "downloaded_count": 0,
            "output_dir": str(query_output_root),
            "output_path": None,
            "fasta_path": None,
            "metadata_path": None,
            "query_translation": search.get("query_translation"),
            "message": "No NCBI records matched the search term.",
        }

    if filename:
        output_name = Path(filename).name
    else:
        output_name = f"{output_stem}.fasta"
    output_path = query_output_root / output_name

    if metadata_filename:
        metadata_name = Path(metadata_filename).name
    else:
        metadata_name = f"{output_stem}.metadata.csv"
    metadata_path = query_output_root / metadata_name

    _download_from_history(
        db=db,
        query_key=search["query_key"],
        webenv=search["webenv"],
        download_count=search["download_count"],
        output_path=output_path,
        email=email,
        api_key=api_key,
    )

    metadata = _download_metadata_from_history(
        db=db,
        query_key=search["query_key"],
        webenv=search["webenv"],
        download_count=search["download_count"],
        output_path=metadata_path,
        email=email,
        api_key=api_key,
        label=label,
        subtype=subtype,
    )
    fasta_records = _normalize_fasta_headers(
        output_path,
        sequence_names=[record["strain"] for record in metadata],
    )
    metadata_records = len(metadata)

    return {
        "term": clean_term,
        "db": db,
        "sequence_format": "fasta",
        "metadata_format": "csv",
        "matched_count": search["count"],
        "downloaded_count": search["download_count"],
        "output_dir": str(query_output_root),
        "output_path": str(output_path),
        "fasta_path": str(output_path),
        "metadata_path": str(metadata_path),
        "bytes_written": output_path.stat().st_size,
        "fasta_records": fasta_records,
        "metadata_records": metadata_records,
        "metadata_bytes_written": metadata_path.stat().st_size,
        "query_translation": search.get("query_translation"),
    }
