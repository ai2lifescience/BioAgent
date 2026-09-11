"""AlphaFold Protein Structure Database adapter."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import requests

from bio_data.api_http import request_api, response_provenance, validate_api_url


ALPHAFOLD_API_BASE = "https://alphafold.ebi.ac.uk/api"
ACCESSION_PATTERN = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$",
    re.IGNORECASE,
)


def query_alphafold(
    query: str,
    max_results: int = 5,
    download: bool = False,
    output_dir: str | None = None,
    file_format: str = "cif",
) -> dict[str, Any]:
    accession = query.strip().upper()
    if not ACCESSION_PATTERN.fullmatch(accession):
        raise ValueError("AlphaFold lookup requires a UniProt-style accession.")
    clean_format = file_format.strip().lower().lstrip(".")
    if clean_format == "mmcif":
        clean_format = "cif"
    if clean_format not in {"cif", "pdb"}:
        raise ValueError("AlphaFold file_format must be 'cif' or 'pdb'.")

    url = f"{ALPHAFOLD_API_BASE}/prediction/{accession}"
    try:
        payload = request_api("GET", url).json()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return {
                "database": "alphafold",
                "query": accession,
                "operation": "prediction_lookup",
                "record_count": 0,
                "records": [],
                "artifacts": [],
                "provenance": response_provenance(url, "prediction_lookup"),
                "warnings": ["No AlphaFold Database prediction was found for this accession."],
            }
        raise
    raw_records = payload if isinstance(payload, list) else [payload]
    limit = max(1, min(int(max_results), 25))
    records = [_normalize_alphafold_record(item) for item in raw_records[:limit] if isinstance(item, dict)]
    artifacts: list[dict[str, Any]] = []
    if download and records:
        selected_url = records[0].get(f"{clean_format}_url")
        if not selected_url:
            raise RuntimeError(f"AlphaFold entry did not provide a {clean_format.upper()} download URL.")
        validate_api_url(str(selected_url))
        response = request_api("GET", str(selected_url), accept="application/octet-stream")
        destination = Path(output_dir or "runtime/alphafold")
        destination.mkdir(parents=True, exist_ok=True)
        entry_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(records[0].get("entry_id") or accession))
        output_path = destination / f"{entry_id}.{clean_format}"
        output_path.write_bytes(response.content)
        artifacts.append(
            {
                "kind": "structure",
                "path": str(output_path),
                "url": selected_url,
                "bytes": output_path.stat().st_size,
            }
        )

    return {
        "database": "alphafold",
        "query": accession,
        "operation": "prediction_lookup",
        "record_count": len(records),
        "records": records,
        "artifacts": artifacts,
        "provenance": response_provenance(url, "prediction_lookup"),
        "warnings": [] if records else ["No AlphaFold Database prediction was found for this accession."],
    }


def _normalize_alphafold_record(item: dict[str, Any]) -> dict[str, Any]:
    record = {
        "entry_id": item.get("entryId"),
        "uniprot_accession": item.get("uniprotAccession"),
        "uniprot_id": item.get("uniprotId"),
        "gene": item.get("gene"),
        "protein_name": item.get("uniprotDescription") or item.get("proteinDescription"),
        "organism": item.get("organismScientificName"),
        "taxid": item.get("taxId"),
        "model_created": item.get("modelCreatedDate"),
        "latest_version": item.get("latestVersion"),
        "mean_plddt": item.get("globalMetricValue"),
        "pdb_url": item.get("pdbUrl"),
        "cif_url": item.get("cifUrl"),
        "bcif_url": item.get("bcifUrl"),
        "pae_url": item.get("paeDocUrl"),
    }
    return {key: value for key, value in record.items() if value not in (None, "", [])}
