"""NCBI GenBank metadata parsing and writing helpers."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from bio_data.ncbi_entrez.http import _base_params, _request_get
from bio_data.ncbi_entrez.spec import DEFAULT_BATCH_SIZE

def _gbseq_metadata_records(
    root: ET.Element,
    label: str | None = None,
    subtype: str | None = None,
) -> list[dict[str, Any]]:
    return [
        _gbseq_metadata_record(seq, label=label, subtype=subtype)
        for seq in root.findall(".//GBSeq")
    ]

def _gbseq_metadata_record(
    seq: ET.Element,
    label: str | None = None,
    subtype: str | None = None,
) -> dict[str, Any]:
    source_qualifiers = _source_qualifiers(seq)
    geo_loc_name = _first_value(source_qualifiers, "geo_loc_name", "country")
    accession = seq.findtext("GBSeq_accession-version") or seq.findtext("GBSeq_primary-accession") or ""
    collection_date = _first_value(source_qualifiers, "collection_date")
    source_strain = _first_value(source_qualifiers, "strain")
    strain = source_strain or accession
    return {
        "strain": strain,
        "date": collection_date,
        "region": _region_from_geo_loc(geo_loc_name),
        "country": _country_from_geo_loc(geo_loc_name),
        "host": _first_value(source_qualifiers, "host"),
        "subtype": subtype or "",
        "segment": label or "",
        "query_label": label or "",
        "accessionversion": accession,
        "primary_accession": seq.findtext("GBSeq_primary-accession") or "",
        "title": seq.findtext("GBSeq_definition") or "",
        "organism": seq.findtext("GBSeq_organism") or _first_value(source_qualifiers, "organism"),
        "geo_loc_name": geo_loc_name,
        "collection_date": collection_date,
        "isolation_source": _first_value(source_qualifiers, "isolation_source"),
        "source_strain": source_strain,
        "isolate": _first_value(source_qualifiers, "isolate"),
        "clone": _first_value(source_qualifiers, "clone"),
        "moltype": _first_value(source_qualifiers, "mol_type"),
        "topology": seq.findtext("GBSeq_topology") or "",
        "slen": seq.findtext("GBSeq_length") or "",
        "created": seq.findtext("GBSeq_create-date") or "",
        "updated": seq.findtext("GBSeq_update-date") or "",
        "taxonomy": seq.findtext("GBSeq_taxonomy") or "",
        "source_qualifiers": json.dumps(source_qualifiers, ensure_ascii=False, sort_keys=True),
    }

def _source_qualifiers(seq: ET.Element) -> dict[str, list[str]]:
    qualifiers: dict[str, list[str]] = {}
    for feature in seq.findall(".//GBFeature"):
        if feature.findtext("GBFeature_key") != "source":
            continue
        for qualifier in feature.findall(".//GBQualifier"):
            name = qualifier.findtext("GBQualifier_name")
            if not name:
                continue
            qualifiers.setdefault(name, []).append(qualifier.findtext("GBQualifier_value") or "")
        break
    return qualifiers

def _first_value(values: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        for value in values.get(key, []):
            if value:
                return value
    return ""

def _country_from_geo_loc(value: str) -> str:
    if not value:
        return ""
    return value.split(":", 1)[0].strip()

def _region_from_geo_loc(value: str) -> str:
    if not value or ":" not in value:
        return ""
    return value.split(":", 1)[1].split(",", 1)[0].strip()

def _metadata_fieldnames(records: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "strain",
        "date",
        "region",
        "country",
        "host",
        "subtype",
        "segment",
        "query_label",
        "accessionversion",
        "primary_accession",
        "title",
        "organism",
        "geo_loc_name",
        "collection_date",
        "isolation_source",
        "source_strain",
        "isolate",
        "clone",
        "slen",
        "moltype",
        "topology",
        "created",
        "updated",
        "taxonomy",
        "source_qualifiers",
    ]
    seen = {key for record in records for key in record}
    ordered = [key for key in preferred if key in seen]
    ordered.extend(sorted(seen - set(ordered)))
    return ordered or preferred

def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)

def _download_metadata_from_history(
    db: str,
    query_key: str,
    webenv: str,
    download_count: int,
    output_path: Path,
    email: str | None,
    api_key: str | None,
    label: str | None = None,
    subtype: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for retstart in range(0, download_count, batch_size):
        retmax = min(batch_size, download_count - retstart)
        params: dict[str, Any] = {
            **_base_params(email=email, api_key=api_key),
            "db": db,
            "query_key": query_key,
            "WebEnv": webenv,
            "retstart": retstart,
            "retmax": retmax,
            "rettype": "gb",
            "retmode": "xml",
        }
        response = _request_get("efetch.fcgi", params)
        root = ET.fromstring(response.content)
        records.extend(_gbseq_metadata_records(root, label=label, subtype=subtype))
        if retstart + retmax < download_count:
            time.sleep(0.34)

    fieldnames = _metadata_fieldnames(records)
    with output_path.open("w", encoding="utf-8", newline="") as output_handle:
        writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: _csv_value(record.get(key)) for key in fieldnames})
    return records
