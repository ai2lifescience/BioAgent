"""RCSB PDB search and download adapter."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import requests


RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_DOWNLOAD_URL_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.{file_format}"
REQUEST_TIMEOUT = 30
SUPPORTED_STRUCTURE_FORMATS = {"cif", "pdb", "bcif"}


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
