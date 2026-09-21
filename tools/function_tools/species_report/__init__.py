"""Build a trusted-source report about a species or biological entity.

Use when the user asks for a synthesized explanation, literature
summary, or Markdown report with citations. Do not use for raw NCBI records,
database lookup, BLAST, or one-step sequence analysis.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import species_report as _workflow
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.results import run_workflow
from tools.infrastructure.tool_support.decorators import bio_function_tool


@bio_function_tool()
async def species_report(
    ctx: RunContextWrapper[AgentRunContext],
    species_name: Annotated[str | None, Field(description="Species, organism, virus, phage, or biological entity name to research, for example 'PhiX174' or 'SARS-CoV-2'.")] = None,
    species: Annotated[str | None, Field(description='Alias for species_name.')] = None,
    question: Annotated[str | None, Field(description='Specific research question or concern.')] = None,
    concerns: Annotated[list[str] | None, Field(description='Optional focus areas such as genome structure, host range, replication, mutations, or applications.')] = None,
    max_pubmed: Annotated[int, Field(description='Maximum PubMed records to collect.', ge=1)] = 6,
    max_web_pages: Annotated[int, Field(description='Maximum trusted web pages to collect.', ge=0)] = 6,
    top_k: Annotated[int, Field(description='Number of Chroma chunks retrieved for RAG.', ge=1)] = 6,
    collection_name: Annotated[str | None, Field(description='Optional Chroma collection name. Defaults to a safe name derived from the species.')] = None,
    chroma_path: Annotated[str | None, Field(description='Session-relative Chroma storage directory; defaults to the current run directory. Paths outside the session are rejected.')] = None,
    output_dir: Annotated[str | None, Field(description='Session-relative report directory; defaults to outputs/reports. Paths outside the session are rejected.')] = None,
) -> str:
    """Build a cited species or organism knowledge report.

    Use for a trusted-source organism report or literature synthesis with
    citations. Collects PubMed and trusted web evidence, synthesizes it, and
    writes a Markdown report. Use ncbi_retrieval for raw sequence records,
    database_lookup for a database query, and genome_map for a genome image.
    Answer general conceptual questions directly when evidence retrieval or
    a saved report is not requested.
    """
    return await run_workflow(ctx.context, 'species_report', _workflow,
        {'species_name': species_name, 'species': species, 'question': question, 'concerns': concerns, 'max_pubmed': max_pubmed, 'max_web_pages': max_web_pages, 'top_k': top_k, 'collection_name': collection_name, 'chroma_path': chroma_path, 'output_dir': output_dir}, category='species_report',
        with_progress=True)
