"""Literature and gene-disease evidence review route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute


LITERATURE_EVIDENCE_TERMS = (
    "evidence",
    "literature",
    "pubmed",
    "papers",
    "paper",
    "studies",
    "study",
    "clinical",
    "conflict",
    "conflicts",
    "conflicting",
)
GENE_DISEASE_CONTEXT_TERMS = (
    "gene",
    "genes",
    "variant",
    "variants",
    "mutation",
    "mutations",
    "disease",
    "diseases",
    "cancer",
    "syndrome",
    "phenotype",
    "biomarker",
    "association",
    "associated",
    "therapy",
    "treatment",
    "drug",
    "cohort",
)


def route_literature_evidence_review(user_request: str) -> IntentRoute | None:
    if not is_literature_evidence_review_request(user_request):
        return None
    return IntentRoute(
        mode="llm_skill_loop",
        arguments={
            "task_type": "literature_evidence_review",
            "question": user_request,
        },
        reason=(
            "Matched a literature or gene-disease evidence review request, "
            "not an organism species-report request."
        ),
    )


def is_literature_evidence_review_request(text: str) -> bool:
    literature = "|".join(re.escape(term) for term in LITERATURE_EVIDENCE_TERMS)
    gene_disease = "|".join(re.escape(term) for term in GENE_DISEASE_CONTEXT_TERMS)
    if not re.search(rf"\b(?:{literature})\b", text, re.IGNORECASE):
        return False
    if re.search(rf"\b(?:{gene_disease})\b", text, re.IGNORECASE):
        return True
    return bool(
        re.search(
            r"\b(?:for|about|on)\s+[A-Za-z0-9_.-]+\s+(?:in|and|with)\s+"
            r"[A-Za-z0-9_.-]+(?:\s+[A-Za-z0-9_.-]+){0,4}\s+"
            r"(?:disease|cancer|syndrome)\b",
            text,
            re.IGNORECASE,
        )
    )
