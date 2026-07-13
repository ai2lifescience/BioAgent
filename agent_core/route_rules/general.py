"""General interface and direct-response route rules."""

from __future__ import annotations

import re

from agent_core.router import IntentRoute


LLM_RESPONSE_TERMS = (
    "what is",
    "what are",
    "explain",
    "define",
    "describe",
    "overview",
    "how does",
    "how do",
    "why does",
    "why do",
    "concept",
    "conceptually",
    "meaning of",
)
TOOL_SEEKING_TERMS = (
    "analyze",
    "analyse",
    "blast",
    "citation",
    "citations",
    "collect",
    "compare",
    "contrast",
    "download",
    "evidence",
    "fetch",
    "file",
    "find",
    "inspect",
    "literature",
    "pipeline",
    "pubmed",
    "rag",
    "records",
    "report",
    "retrieve",
    "run",
    "search",
    "sources",
    "trusted",
)


def route_control_response(user_request: str) -> IntentRoute | None:
    clean = user_request.strip().lower()
    if clean in {"hi", "hello", "hey"}:
        return IntentRoute(
            mode="control_response",
            arguments={
                "answer": (
                    "Hello. BioAgent can retrieve NCBI records, search UniProt/PDB, "
                    "analyze sequences, inspect output files, run BLAST, and build "
                    "trusted-source species reports."
                )
            },
            reason="Matched a simple interface control request that does not need tools.",
        )
    if clean in {"help", "--help", "/help"} or re.search(r"\b(what can you do|capabilities)\b", clean):
        return IntentRoute(
            mode="control_response",
            arguments={
                "answer": (
                    "BioAgent capabilities: NCBI FASTA/metadata retrieval, UniProt/PDB "
                    "lookup, deterministic sequence analysis, BLAST submission, FASTA/CSV "
                    "file inspection, PubMed/RAG-backed species reports, evidence "
                    "collection, trace events, and verification warnings."
                )
            },
            reason="Matched a simple interface control request that does not need tools.",
        )
    return None


def route_llm_response(user_request: str) -> IntentRoute | None:
    clean = user_request.strip().lower()
    response_terms = "|".join(re.escape(term) for term in LLM_RESPONSE_TERMS)
    if not re.search(rf"\b(?:{response_terms})\b", clean):
        return None

    tool_terms = "|".join(re.escape(term) for term in TOOL_SEEKING_TERMS)
    if re.search(rf"\b(?:{tool_terms})\b", clean):
        return None

    return IntentRoute(
        mode="llm_response",
        arguments={"question": user_request},
        reason="Matched an explanatory chatbot-style request that does not need tools.",
    )
