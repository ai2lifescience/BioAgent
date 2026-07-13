"""Biological database lookup route rules."""

from __future__ import annotations

import re
from typing import Any

from agent_core.router import IntentRoute

from .common import extract_labeled_value


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
    database_match = re.search(r"\b(uniprot|pdb)\b", user_request, re.IGNORECASE)
    if not database_match:
        return None
    database = database_match.group(1).lower()
    query = extract_labeled_value(user_request, "query")
    if not query:
        query = re.sub(
            r"\b(search|lookup|find|in|from|for|uniprot|pdb|database|records?|entries?|hits?)\b",
            " ",
            user_request,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"\b\d+\b", " ", query)
        query = re.sub(r"\s+", " ", query).strip(" .,:;")
    if not query:
        return None
    limit_match = re.search(r"\b(\d+)\s*(?:records?|entries?|hits?)\b", user_request, re.IGNORECASE)
    args: dict[str, Any] = {"database": database, "query": query}
    if limit_match:
        args["max_results"] = max(1, int(limit_match.group(1)))
    return IntentRoute(
        mode="direct_skill",
        skill_name="database_lookup",
        arguments=args,
        reason="Matched a UniProt/PDB database lookup request.",
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


def _normalize_requested_format(value: str) -> str:
    clean = value.lower()
    return "cif" if clean == "mmcif" else clean
