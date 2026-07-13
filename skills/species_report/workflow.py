"""Species report skill workflow."""

from __future__ import annotations

import os
from typing import Any, Callable

from execution.skill_context import SkillContext, ensure_skill_context
from skills.species_report.utils import (
    build_research_question,
    build_source_query,
    collection_name_for,
    normalize_text,
    source_summary,
)


DEFAULT_MAX_PUBMED = 6
DEFAULT_MAX_WEB_PAGES = 6
DEFAULT_TOP_K = 6
DEFAULT_CHROMA_PATH = os.getenv("BIOAGENT_CHROMA_PATH", "runtime/chroma")
DEFAULT_OUTPUT_DIR = os.getenv("BIOAGENT_REPORT_DIR", "runtime/reports")

SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "species_report",
        "description": (
            "Build a trusted-source species or organism knowledge report using "
            "PubMed, trusted web collection, RAG retrieval, LLM synthesis, and "
            "Markdown file output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "species_name": {
                    "type": "string",
                    "description": (
                        "Species, organism, virus, phage, or biological entity name "
                        "to research, for example 'PhiX174' or 'SARS-CoV-2'."
                    ),
                },
                "species": {
                    "type": "string",
                    "description": "Alias for species_name.",
                },
                "question": {
                    "type": "string",
                    "description": "Specific research question or concern.",
                },
                "concerns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional focus areas such as genome structure, host range, "
                        "replication, mutations, or applications."
                    ),
                },
                "max_pubmed": {
                    "type": "integer",
                    "description": "Maximum PubMed records to collect.",
                    "default": DEFAULT_MAX_PUBMED,
                    "minimum": 1,
                },
                "max_web_pages": {
                    "type": "integer",
                    "description": "Maximum trusted web pages to collect.",
                    "default": DEFAULT_MAX_WEB_PAGES,
                    "minimum": 0,
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of Chroma chunks retrieved for RAG.",
                    "default": DEFAULT_TOP_K,
                    "minimum": 1,
                },
                "collection_name": {
                    "type": "string",
                    "description": (
                        "Optional Chroma collection name. Defaults to a safe name "
                        "derived from the species."
                    ),
                },
                "chroma_path": {
                    "type": "string",
                    "description": "Directory for persistent Chroma storage.",
                    "default": DEFAULT_CHROMA_PATH,
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory where the Markdown report is saved.",
                    "default": DEFAULT_OUTPUT_DIR,
                },
            },
            "required": ["species_name"],
            "additionalProperties": False,
        },
    },
}


def _emit(log_fn: Callable[[str], None] | None, message: str) -> None:
    if log_fn:
        log_fn(f"[species_report] {message}")


def species_report(
    species_name: str | None = None,
    species: str | None = None,
    question: str | None = None,
    concerns: list[str] | None = None,
    max_pubmed: int = DEFAULT_MAX_PUBMED,
    max_web_pages: int = DEFAULT_MAX_WEB_PAGES,
    top_k: int = DEFAULT_TOP_K,
    collection_name: str | None = None,
    chroma_path: str = DEFAULT_CHROMA_PATH,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    context: SkillContext | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "species_report")
    if chroma_path == DEFAULT_CHROMA_PATH:
        chroma_path = context.runtime_path("chroma")
    if output_dir == DEFAULT_OUTPUT_DIR:
        output_dir = context.artifact_path("reports")

    resolved_species = normalize_text(species_name or species or "")
    if not resolved_species:
        raise ValueError("species_name or species is required.")
    if max_pubmed < 1:
        raise ValueError("max_pubmed must be at least 1.")
    if max_web_pages < 0:
        raise ValueError("max_web_pages cannot be negative.")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    research_question = build_research_question(
        species_name=resolved_species,
        question=question,
        concerns=concerns,
    )
    source_query = build_source_query(question=question, concerns=concerns)

    _emit(log_fn, f"Collecting PubMed records for {resolved_species}.")
    pubmed_result = context.run_tool(
        "pubmed_collect",
        {
            "species_name": resolved_species,
            "question": source_query,
            "max_records": max_pubmed,
        }
    )["result"]
    _emit(log_fn, f"Collected {pubmed_result.get('record_count', 0)} PubMed record(s).")

    _emit(log_fn, f"Collecting up to {max_web_pages} trusted web page(s).")
    web_result = context.run_tool(
        "trusted_web_collect",
        {
            "species_name": resolved_species,
            "question": source_query,
            "max_pages": max_web_pages,
        }
    )["result"]
    _emit(log_fn, f"Collected {web_result.get('record_count', 0)} trusted web page(s).")

    records = [
        *pubmed_result.get("records", []),
        *web_result.get("records", []),
    ]
    if not records:
        raise RuntimeError(
            f"No trusted source records were found for '{resolved_species}'. "
            "Try a broader species name or concern."
        )

    _emit(log_fn, f"Chunking {len(records)} source record(s).")
    chunk_result = context.run_tool("rag_chunk", {"records": records})["result"]
    chunks = chunk_result.get("chunks", [])
    if not chunks:
        raise RuntimeError(f"Trusted records for '{resolved_species}' had no usable text.")
    _emit(log_fn, f"Created {len(chunks)} text chunk(s).")

    resolved_collection_name = collection_name_for(resolved_species, collection_name)
    _emit(
        log_fn,
        f"Embedding chunks and storing them in Chroma collection {resolved_collection_name}.",
    )
    context.run_tool(
        "rag_store",
        {
            "records": chunks,
            "collection_name": resolved_collection_name,
            "chroma_path": chroma_path,
        }
    )

    _emit(log_fn, "Retrieving ranked RAG evidence chunks.")
    retrieve_result = context.run_tool(
        "rag_retrieve",
        {
            "question": research_question,
            "collection_name": resolved_collection_name,
            "chroma_path": chroma_path,
            "top_k": min(top_k, len(chunks)),
        }
    )["result"]
    _emit(log_fn, f"Retrieved {retrieve_result.get('chunk_count', 0)} ranked chunk(s).")

    citation_result = context.run_tool(
        "rag_citations",
        {
            "chunks": retrieve_result.get("chunks", []),
        }
    )["result"]
    retrieval_context = citation_result.get("context") or retrieve_result.get("context", "")

    _emit(log_fn, "Requesting parallel direct LLM opinions.")
    model_opinion_result = context.run_tool(
        "species_model_opinions",
        {
            "species_name": resolved_species,
            "question": research_question,
        }
    )["result"]
    sources = source_summary(records)

    _emit(log_fn, "Synthesizing final Markdown report.")
    synthesis_result = context.run_tool(
        "species_report_synthesis",
        {
            "species_name": resolved_species,
            "question": research_question,
            "retrieval_context": retrieval_context,
            "model_answers": model_opinion_result["model_answers"],
            "sources": sources,
        }
    )["result"]

    writer_result = context.run_tool(
        "markdown_report_writer",
        {
            "markdown": synthesis_result["markdown"],
            "entity_name": resolved_species,
            "output_dir": output_dir,
            "suffix": "knowledge",
        }
    )["result"]
    _emit(log_fn, f"Report saved to {writer_result['report_path']}.")

    return {
        "skill": "species_report",
        "species": resolved_species,
        "species_name": resolved_species,
        "question": research_question,
        "answer": synthesis_result["markdown"],
        "report_path": writer_result["report_path"],
        "collection_name": resolved_collection_name,
        "chroma_path": chroma_path,
        "source_count": len(records),
        "chunk_count": len(chunks),
        "sources": sources,
        "retrieval_context": retrieval_context,
        "retrieved_chunks": retrieve_result.get("chunks", []),
        "citations": citation_result.get("citations", []),
        "model_answers": model_opinion_result["model_answers"],
    }
