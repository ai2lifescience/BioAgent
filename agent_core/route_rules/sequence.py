"""Sequence analysis and BLAST route rules."""

from __future__ import annotations

import re
from typing import Any

from agent_core.router import IntentRoute

from .common import extract_quoted_or_labeled_path, extract_sequence


def _extract_blast_rid(user_request: str) -> str | None:
    match = re.search(r"\bRID\s*(?::|=)?\s*([A-Z0-9-]{8,})\b", user_request, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _asks_for_blast_results(user_request: str) -> bool:
    return bool(
        re.search(
            r"\b(wait|poll|ready|results?|hits?|top hits?|alignments?)\b",
            user_request,
            re.IGNORECASE,
        )
    )


def route_blast(user_request: str) -> IntentRoute | None:
    if not re.search(r"\bblast\b", user_request, re.IGNORECASE):
        return None
    rid = _extract_blast_rid(user_request)
    if rid:
        return IntentRoute(
            mode="direct_skill",
            skill_name="blast_search",
            arguments={"rid": rid, "wait": True},
            reason="Matched a BLAST RID polling request.",
        )
    sequence = extract_sequence(user_request)
    if not sequence:
        return None
    program_match = re.search(r"\b(blastn|blastp|blastx|tblastn|tblastx)\b", user_request, re.IGNORECASE)
    database_match = re.search(r"\b(?:database|db)\s*(?::|=)?\s*([A-Za-z0-9_]+)\b", user_request, re.IGNORECASE)
    args: dict[str, Any] = {"sequence": sequence}
    if program_match:
        args["program"] = program_match.group(1).lower()
    if database_match:
        args["database"] = database_match.group(1)
    if _asks_for_blast_results(user_request):
        args["wait"] = True
    return IntentRoute(
        mode="direct_skill",
        skill_name="blast_search",
        arguments=args,
        reason="Matched an explicit BLAST request.",
    )


def route_sequence_analysis(user_request: str) -> IntentRoute | None:
    if not re.search(
        r"\b(analy[sz]e|gc content|orf|base count|residue count|sequence length|fasta summary)\b",
        user_request,
        re.IGNORECASE,
    ):
        return None
    path = extract_quoted_or_labeled_path(user_request)
    if path:
        if not path.lower().endswith((".fasta", ".fa", ".fna", ".faa")):
            return None
        return IntentRoute(
            mode="direct_skill",
            skill_name="sequence_analysis",
            arguments={"fasta_path": path},
            reason="Matched a deterministic sequence analysis request.",
        )
    sequence = extract_sequence(user_request)
    if not sequence:
        if re.search(
            r"\b(latest|last|previous|downloaded|just downloaded|that fasta|the fasta)\b",
            user_request,
            re.IGNORECASE,
        ):
            return IntentRoute(
                mode="direct_skill",
                skill_name="sequence_analysis",
                arguments={"artifact_ref": "latest_fasta"},
                reason="Matched a sequence analysis request for the latest session FASTA artifact.",
            )
        return None
    return IntentRoute(
        mode="direct_skill",
        skill_name="sequence_analysis",
        arguments={"sequence": sequence},
        reason="Matched a deterministic sequence analysis request.",
    )
