"""RCSB PDB search and download adapter."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import requests

from bio_data.api_http import request_api, response_provenance


RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_DATA_URL_TEMPLATE = "https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
RCSB_DOWNLOAD_URL_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.{file_format}"
REQUEST_TIMEOUT = 30
SUPPORTED_STRUCTURE_FORMATS = {"cif", "pdb", "bcif"}
PDB_QUERY_OPERATIONS = {"search", "entry", "entry_details", "details"}


def normalize_pdb_id(pdb_id: str) -> str:
    clean_id = pdb_id.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", clean_id):
        raise ValueError("pdb_id must be a four-character PDB identifier, for example 1A3N.")
    return clean_id


def normalize_structure_format(file_format: str = "cif") -> str:
    clean_format = file_format.strip().lower().lstrip(".")
    if clean_format == "mmcif":
        clean_format = "cif"
    if clean_format not in SUPPORTED_STRUCTURE_FORMATS:
        allowed = ", ".join(sorted(SUPPORTED_STRUCTURE_FORMATS))
        raise ValueError(f"file_format must be one of: {allowed}.")
    return clean_format


def search_pdb(query: str, max_results: int = 5) -> dict[str, Any]:
    payload = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": query},
        },
        "request_options": {
            "paginate": {"start": 0, "rows": max(1, min(max_results, 25))},
            "results_content_type": ["experimental"],
        },
        "return_type": "entry",
    }
    response = requests.post(RCSB_SEARCH_URL, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    records = []
    for item in data.get("result_set", []):
        identifier = item.get("identifier", "")
        records.append(
            {
                "identifier": identifier,
                "id": identifier,
                "score": item.get("score"),
                "url": f"https://www.rcsb.org/structure/{identifier}" if identifier else "",
            }
        )
    return {
        "database": "pdb",
        "query": query,
        "record_count": len(records),
        "records": records,
    }


def get_pdb_entry(pdb_id: str) -> dict[str, Any]:
    """Retrieve normalized metadata for one exact PDB identifier."""
    clean_id = normalize_pdb_id(pdb_id)
    url = RCSB_DATA_URL_TEMPLATE.format(pdb_id=clean_id)
    payload = request_api("GET", url).json()
    entry_info = payload.get("rcsb_entry_info", {})
    accession_info = payload.get("rcsb_accession_info", {})
    struct = payload.get("struct", {})
    exptl = payload.get("exptl", [])
    methods = [item.get("method") for item in exptl if isinstance(item, dict) and item.get("method")]
    record = {
        "identifier": clean_id,
        "id": clean_id,
        "title": struct.get("title"),
        "experimental_methods": methods,
        "resolution_combined": entry_info.get("resolution_combined"),
        "polymer_entity_count": entry_info.get("polymer_entity_count"),
        "nonpolymer_entity_count": entry_info.get("nonpolymer_entity_count"),
        "deposit_date": accession_info.get("deposit_date"),
        "initial_release_date": accession_info.get("initial_release_date"),
        "url": f"https://www.rcsb.org/structure/{clean_id}",
    }
    record = {key: value for key, value in record.items() if value not in (None, "", [])}
    return {
        "database": "pdb",
        "query": clean_id,
        "operation": "entry_details",
        "record_count": 1,
        "records": [record],
        "provenance": response_provenance(url, "entry_details"),
        "warnings": [],
    }


def query_pdb(
    query: str,
    max_results: int = 5,
    operation: str | None = None,
    download: bool = False,
    file_format: str = "cif",
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Search RCSB PDB or retrieve one exact entry and optional structure file."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("PDB query must not be empty.")
    clean_operation = (operation or "").strip().lower().replace("-", "_")
    if clean_operation and clean_operation not in PDB_QUERY_OPERATIONS:
        allowed = ", ".join(sorted(PDB_QUERY_OPERATIONS))
        raise ValueError(f"PDB operation must be one of: {allowed}.")

    exact_identifier = bool(re.fullmatch(r"[0-9][A-Z0-9]{3}", clean_query, re.IGNORECASE))
    entry_lookup = download or clean_operation in {"entry", "entry_details", "details"}
    if not clean_operation and exact_identifier:
        entry_lookup = True
    if entry_lookup:
        result = get_pdb_entry(clean_query)
        if download:
            artifact = download_pdb_structure(
                clean_query,
                file_format=file_format,
                output_dir=output_dir or "runtime/pdb",
            )
            result["artifacts"] = [artifact]
        return result

    result = search_pdb(clean_query, max_results=max_results)
    result["operation"] = "search"
    result["provenance"] = response_provenance(RCSB_SEARCH_URL, "search")
    result["warnings"] = []
    return result


def download_pdb_structure(
    pdb_id: str,
    file_format: str = "cif",
    output_dir: str = "runtime/pdb",
) -> dict[str, Any]:
    clean_id = normalize_pdb_id(pdb_id)
    clean_format = normalize_structure_format(file_format)
    url = RCSB_DOWNLOAD_URL_TEMPLATE.format(
        pdb_id=clean_id,
        file_format=clean_format,
    )
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError(f"RCSB PDB returned an empty file for {clean_id}.{clean_format}.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    structure_path = output_path / f"{clean_id}.{clean_format}"
    structure_path.write_bytes(response.content)

    return {
        "status": "ok",
        "database": "pdb",
        "pdb_id": clean_id,
        "identifier": clean_id,
        "file_format": clean_format,
        "url": url,
        "structure_path": str(structure_path),
        "output_dir": str(output_path),
        "bytes": structure_path.stat().st_size,
    }
