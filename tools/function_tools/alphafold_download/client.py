"""Standalone AlphaFold Database download client for this plug-in."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import requests

from tools.common.http import request_http, response_provenance, validate_https_url


ALPHAFOLD_API_BASE = "https://alphafold.ebi.ac.uk/api"
ALPHAFOLD_ALLOWED_HOSTS = frozenset(
    {"alphafold.ebi.ac.uk", "www.alphafold.ebi.ac.uk", "ftp.ebi.ac.uk"}
)
ACCESSION_PATTERN = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$",
    re.IGNORECASE,
)


def download_alphafold_structure(
    accession: str,
    output_dir: str,
    file_format: str = "cif",
) -> dict[str, Any]:
    clean_accession = accession.strip().upper()
    if not ACCESSION_PATTERN.fullmatch(clean_accession):
        raise ValueError("accession must be a UniProt-style AlphaFold accession.")
    clean_format = file_format.strip().lower().lstrip(".")
    if clean_format == "mmcif":
        clean_format = "cif"
    if clean_format not in {"cif", "pdb"}:
        raise ValueError("file_format must be 'cif' or 'pdb'.")

    metadata_url = f"{ALPHAFOLD_API_BASE}/prediction/{clean_accession}"
    try:
        payload = request_http("GET", metadata_url, allowed_hosts=ALPHAFOLD_ALLOWED_HOSTS).json()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError(f"No AlphaFold prediction was found for {clean_accession}.") from exc
        raise
    raw_record = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(raw_record, dict):
        raise ValueError(f"No AlphaFold prediction was found for {clean_accession}.")
    url_key = "cifUrl" if clean_format == "cif" else "pdbUrl"
    structure_url = raw_record.get(url_key)
    if not structure_url:
        raise RuntimeError(f"AlphaFold entry did not provide a {clean_format.upper()} download URL.")
    validate_https_url(str(structure_url), allowed_hosts=ALPHAFOLD_ALLOWED_HOSTS)
    response = request_http(
        "GET",
        str(structure_url),
        allowed_hosts=ALPHAFOLD_ALLOWED_HOSTS,
        accept="application/octet-stream",
    )
    entry_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(raw_record.get("entryId") or clean_accession))
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / f"{entry_id}.{clean_format}"
    output_path.write_bytes(response.content)
    return {
        "database": "alphafold",
        "query": clean_accession,
        "operation": "prediction_download",
        "record_count": 1,
        "structure_path": str(output_path),
        "files": [{"kind": "structure", "path": str(output_path), "url": structure_url, "bytes": output_path.stat().st_size}],
        "provenance": response_provenance(metadata_url, "prediction_download"),
    }
