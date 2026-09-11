"""Biological database lookup route rules."""

from __future__ import annotations

import re
from typing import Any

from agent_core.router import IntentRoute

from .common import extract_labeled_value


DATABASE_NAMES = ("uniprot", "interpro", "kegg", "quickgo", "pdb", "alphafold")


def route_pdb_download(user_request: str) -> IntentRoute | None:
    if not re.search(r"\bpdb\b", user_request, re.IGNORECASE):
        return None
    if not re.search(r"\b(download|fetch|retrieve|save|get)\b", user_request, re.IGNORECASE):
        return None
    pdb_id = _extract_pdb_id(user_request)
    if not pdb_id:
        return None
    args: dict[str, Any] = {"pdb_id": pdb_id}
    format_match = re.search(r"\b(?:as|format)\s*(?:=|:)?\s*(mmcif|cif|pdb|bcif)\b", user_request, re.IGNORECASE)
    extension_match = re.search(r"\.(cif|pdb|bcif)\b", user_request, re.IGNORECASE)
    if format_match:
        args["file_format"] = _normalize_requested_format(format_match.group(1))
    elif extension_match:
        args["file_format"] = extension_match.group(1).lower()

    output_dir = extract_labeled_value(user_request, "output_dir") or extract_labeled_value(user_request, "output")
    if output_dir:
        args["output_dir"] = output_dir

    return IntentRoute(
        mode="direct_skill",
        skill_name="pdb_download",
        arguments=args,
        reason="Matched a PDB structure download request.",
    )


def route_bio_database(user_request: str) -> IntentRoute | None:
    database_match = re.search(
        rf"\b(?:query_)?({'|'.join(DATABASE_NAMES)})\b",
        user_request,
        re.IGNORECASE,
    )
    if not database_match:
        return None
    database = database_match.group(1).lower()
    query = _extract_database_query(user_request)
    if not query:
        query = re.sub(
            rf"\bquery_(?:{'|'.join(DATABASE_NAMES)})\b",
            " ",
            user_request,
            flags=re.IGNORECASE,
        )
        query = re.sub(
            r"\b(search|lookup|find|get|download|retrieve|in|from|for|"
            r"uniprot|interpro|kegg|quickgo|pdb|alphafold|database|records?|"
            r"entries?|entry|hits?|annotations?|domains?|structures?|predictions?)\b",
            " ",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"\btax(?:onomy)?[_ -]?id\b\s*(?::|=)?\s*\d+\b", " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\b(?:as|format)\s*(?::|=)?\s*(?:mmcif|cif|pdb)\b", " ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" .,:;")
    if not query:
        return None
    limit_match = re.search(r"\b(\d+)\s*(?:records?|entries?|hits?)\b", user_request, re.IGNORECASE)
    args: dict[str, Any] = {"database": database, "query": query}
    if limit_match:
        args["max_results"] = max(1, int(limit_match.group(1)))

    operation = extract_labeled_value(user_request, "operation")
    if operation:
        args["operation"] = operation
    elif database == "quickgo" and re.search(r"\bannotations?\b", user_request, re.IGNORECASE):
        args["operation"] = "annotation_search"
    elif database == "interpro" and re.search(r"\bdomains?\b", user_request, re.IGNORECASE):
        args["operation"] = "protein_domains"
    elif database == "pdb" and re.search(r"\b(entry|details?|metadata)\b", user_request, re.IGNORECASE):
        args["operation"] = "entry_details"

    taxid_match = re.search(
        r"\btax(?:onomy)?[_ -]?id\b\s*(?::|=)?\s*(\d+)\b",
        user_request,
        re.IGNORECASE,
    )
    if taxid_match:
        args["taxid"] = int(taxid_match.group(1))

    if database in {"pdb", "alphafold"} and re.search(
        r"\b(download|save)\b", user_request, re.IGNORECASE
    ):
        args["download"] = True
    format_match = re.search(
        r"\b(?:as|format)\s*(?::|=)?\s*(mmcif|cif|pdb)\b",
        user_request,
        re.IGNORECASE,
    )
    if format_match:
        args["file_format"] = "cif" if format_match.group(1).lower() == "mmcif" else format_match.group(1).lower()
    output_dir = extract_labeled_value(user_request, "output_dir") or extract_labeled_value(user_request, "output")
    if output_dir:
        args["output_dir"] = output_dir
    return IntentRoute(
        mode="direct_skill",
        skill_name="database_lookup",
        arguments=args,
        reason=f"Matched a {database} database lookup request.",
    )


def _extract_pdb_id(text: str) -> str | None:
    labeled = re.search(
        r"\b(?:pdb(?:\s+id)?|structure)\b\s*(?::|=)?\s*([A-Za-z0-9]{4})\b",
        text,
        re.IGNORECASE,
    )
    if labeled:
        return labeled.group(1).upper()
    standalone = re.search(r"\b([0-9][A-Za-z0-9]{3})\b", text)
    return standalone.group(1).upper() if standalone else None


def _extract_database_query(text: str) -> str | None:
    """Extract identifiers without dropping namespace colons such as eco:b0002."""
    for label in ("query", "identifier", "accession"):
        quoted = re.search(
            rf"\b{label}\b\s*(?::|=)?\s*(['\"])(.+?)\1",
            text,
            flags=re.IGNORECASE,
        )
        if quoted:
            return quoted.group(2).strip()
        token_pattern = (
            r"([A-Za-z0-9_.+-]*[:/][A-Za-z0-9_.:+/-]+)"
            if label == "query"
            else r"([A-Za-z0-9_.:+/-]+)"
        )
        token = re.search(
            rf"\b{label}\b\s*(?::|=)?\s*{token_pattern}",
            text,
            flags=re.IGNORECASE,
        )
        if token:
            return token.group(1).strip(" .,:;")
        value = extract_labeled_value(text, label)
        if value:
            return value
    return None


def _normalize_requested_format(value: str) -> str:
    clean = value.lower()
    return "cif" if clean == "mmcif" else clean
