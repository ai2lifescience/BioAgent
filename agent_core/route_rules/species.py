"""Species-report route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute

from .common import extract_labeled_value
from .literature import is_literature_evidence_review_request


def route_species_report(user_request: str) -> IntentRoute | None:
    if is_literature_evidence_review_request(user_request):
        return None
    if not re.search(
        r"\b(report|summary|summari[sz]e|trusted sources?|rag|species knowledge|organism information|host range|genome structure|applications?)\b",
        user_request,
        re.IGNORECASE,
    ):
        return None
    species = (
        extract_labeled_value(user_request, "species name")
        or extract_labeled_value(user_request, "organism name")
        or extract_labeled_value(user_request, "species")
        or extract_labeled_value(user_request, "organism")
        or extract_after_preposition(user_request)
    )
    species = clean_species_candidate(species)
    if not species:
        return None
    return IntentRoute(
        mode="direct_skill",
        skill_name="species_report",
        arguments={"species_name": species, "question": user_request},
        reason="Matched a trusted-source species report request.",
    )


def extract_after_preposition(text: str) -> str | None:
    phix = re.search(r"\b(phi\s*x\s*174|phix174)\b", text, re.IGNORECASE)
    if phix:
        return "PhiX174"
    match = re.search(
        r"\b(?:about|for|of|on)\s+([A-Za-z0-9_.-]+(?:\s+[A-Za-z0-9_.-]+){0,3})",
        text,
        re.IGNORECASE,
    )
    if match:
        value = re.split(
            r"\b(?:with|using|from|and|that|which)\b",
            match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return value.strip(" .,:;") or None
    return None


def clean_species_candidate(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip(" .,:;")
    candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(
        r"^(?:species|organism)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"^(?:report|summary|knowledge|information)\s+(?:about|for|of|on)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"^(?:about|for|of|on)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.split(
        r"\b(?:with|using|from|and|that|which|including|include|trusted|sources?|pubmed|rag|report|summary|knowledge|information)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" .,:;")
    if not candidate or candidate.lower() in {"report", "summary", "knowledge", "information"}:
        return None
    if re.search(
        r"^(?:gene|genes|variant|variants|mutation|mutations|disease|diseases|"
        r"cancer|syndrome|phenotype|biomarker|association|therapy|treatment|"
        r"drug|cohort|evidence|literature|papers?|studies?)\b",
        candidate,
        flags=re.IGNORECASE,
    ):
        return None
    if re.search(
        r"\b(?:in|with|for)\s+(?:disease|cancer|syndrome)\b",
        candidate,
        flags=re.IGNORECASE,
    ):
        return None
    if re.fullmatch(r"phi\s*x\s*174|phix174", candidate, flags=re.IGNORECASE):
        return "PhiX174"
    return candidate
