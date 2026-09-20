"""NCBI BLAST URL API adapter."""

from __future__ import annotations

import io
import json
import re
import time
from typing import Any
import zipfile

import requests


BLAST_URL = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
REQUEST_TIMEOUT = 30


def submit_blast_search(
    sequence: str,
    program: str = "blastn",
    database: str = "nt",
    hitlist_size: int = 10,
    expect: float = 10.0,
) -> dict[str, Any]:
    params = {
        "CMD": "Put",
        "PROGRAM": program,
        "DATABASE": database,
        "QUERY": sequence,
        "HITLIST_SIZE": hitlist_size,
        "EXPECT": expect,
    }
    response = requests.post(BLAST_URL, data=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    rid_match = re.search(r"RID\s*=\s*([A-Z0-9-]+)", response.text)
    rtoe_match = re.search(r"RTOE\s*=\s*(\d+)", response.text)
    if not rid_match:
        raise RuntimeError("NCBI BLAST did not return a request ID.")
    return {
        "rid": rid_match.group(1),
        "estimated_seconds": int(rtoe_match.group(1)) if rtoe_match else None,
    }


def poll_blast_search(
    rid: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 10,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status_response = requests.get(
            BLAST_URL,
            params={"CMD": "Get", "RID": rid, "FORMAT_OBJECT": "SearchInfo"},
            timeout=REQUEST_TIMEOUT,
        )
        status_response.raise_for_status()
        status = _parse_status(status_response.text)
        if status == "READY":
            result_response = requests.get(
                BLAST_URL,
                params={"CMD": "Get", "RID": rid, "FORMAT_TYPE": "JSON2"},
                timeout=REQUEST_TIMEOUT,
            )
            result_response.raise_for_status()
            parsed = parse_blast_json2(_extract_blast_result_text(result_response.content, ".json"))
            return {
                "rid": rid,
                "status": "READY",
                "format": "JSON2",
                **parsed,
            }
        if status in {"FAILED", "UNKNOWN"}:
            return {"rid": rid, "status": status, "raw_status": status_response.text}
        time.sleep(max(1, poll_interval_seconds))
    return {"rid": rid, "status": "TIMEOUT", "timeout_seconds": timeout_seconds}


def _parse_status(text: str) -> str:
    match = re.search(r"Status=(\w+)", text)
    return match.group(1).upper() if match else "UNKNOWN"


def parse_blast_json2(raw_text: str) -> dict[str, Any]:
    """Parse NCBI BLAST JSON2 into compact, user-facing hit records."""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "hit_count": 0,
            "hits": [],
            "parse_error": f"Could not parse BLAST JSON2 result: {exc}",
        }

    reports = payload.get("BlastOutput2")
    if isinstance(reports, dict):
        reports = [reports]
    if not isinstance(reports, list):
        return {
            "hit_count": 0,
            "hits": [],
            "parse_error": "BLAST JSON2 result did not contain BlastOutput2.",
        }

    hits: list[dict[str, Any]] = []
    for report_item in reports:
        if not isinstance(report_item, dict):
            continue
        report = report_item.get("report") or {}
        results = report.get("results") or {}
        search = results.get("search") or {}
        for hit in search.get("hits") or []:
            if isinstance(hit, dict):
                hits.append(_parse_hit(hit, len(hits) + 1))

    return {
        "hit_count": len(hits),
        "hits": hits,
    }


def _extract_blast_result_text(content: bytes, suffix: str) -> str:
    """Return the real result file text from plain or zipped NCBI BLAST output."""
    if content.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if name.lower().endswith(suffix.lower())
            ]
            if suffix.lower() == ".json":
                for name in candidates:
                    text = archive.read(name).decode("utf-8", errors="replace")
                    if '"BlastOutput2"' in text:
                        return text
            for name in candidates:
                return archive.read(name).decode("utf-8", errors="replace")
        raise RuntimeError("NCBI BLAST returned a zip file without a result payload.")
    return content.decode("utf-8", errors="replace")


def _parse_hit(hit: dict[str, Any], rank: int) -> dict[str, Any]:
    descriptions = hit.get("description") or []
    description = descriptions[0] if descriptions and isinstance(descriptions[0], dict) else {}
    hsps = hit.get("hsps") or []
    hsp = hsps[0] if hsps and isinstance(hsps[0], dict) else {}
    align_len = _as_int(hsp.get("align_len"))
    identity = _as_int(hsp.get("identity"))
    percent_identity = round(identity * 100 / align_len, 2) if identity is not None and align_len else None

    return {
        "rank": rank,
        "id": description.get("id"),
        "accession": description.get("accession"),
        "title": description.get("title"),
        "scientific_name": description.get("sciname"),
        "taxid": description.get("taxid"),
        "length": _as_int(hit.get("len")),
        "evalue": hsp.get("evalue"),
        "bit_score": hsp.get("bit_score"),
        "score": hsp.get("score"),
        "identity": identity,
        "align_length": align_len,
        "percent_identity": percent_identity,
        "query_range": _range_dict(hsp.get("query_from"), hsp.get("query_to")),
        "hit_range": _range_dict(hsp.get("hit_from"), hsp.get("hit_to")),
    }


def _range_dict(start: Any, end: Any) -> dict[str, int] | None:
    clean_start = _as_int(start)
    clean_end = _as_int(end)
    if clean_start is None or clean_end is None:
        return None
    return {"start": clean_start, "end": clean_end}


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_blast_search(
    sequence: str | None = None,
    rid: str | None = None,
    program: str = "blastn",
    database: str = "nt",
    hitlist_size: int = 10,
    expect: float = 10.0,
    wait: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    if rid:
        result = poll_blast_search(rid=rid, timeout_seconds=timeout_seconds)
        return {
            "database": f"ncbi-blast:{database}",
            "program": program,
            **result,
        }
    if not sequence:
        raise ValueError("sequence or rid is required.")

    submission = submit_blast_search(
        sequence=sequence,
        program=program,
        database=database,
        hitlist_size=hitlist_size,
        expect=expect,
    )
    if not wait:
        return {
            "database": f"ncbi-blast:{database}",
            "program": program,
            "status": "SUBMITTED",
            **submission,
            "message": "BLAST submitted. Call with wait=true to poll for results.",
        }
    result = poll_blast_search(rid=submission["rid"], timeout_seconds=timeout_seconds)
    return {
        "database": f"ncbi-blast:{database}",
        "program": program,
        **submission,
        **result,
    }
