"""Central registry for concrete tools."""

from __future__ import annotations

from tools.base import ToolDefinition
from tools.ask_user import ASK_USER_TOOL
from tools.bio_database import BIO_DATABASE_SEARCH_TOOL
from tools.blast import BLAST_SEARCH_TOOL
from tools.diagnostics import ECHO_TOOL
from tools.file_io import FILE_INSPECT_TOOL, MARKDOWN_REPORT_WRITER_TOOL
from tools.genome_map import GENOME_MAP_TOOL
from tools.literature import PUBMED_COLLECT_TOOL
from tools.ncbi import NCBI_FETCH_TOOL
from tools.pipeline_runner import PIPELINE_RUNNER_TOOL
from tools.pipeline_results import PIPELINE_RESULTS_COLLECT_TOOL
from tools.pdb import PDB_DOWNLOAD_TOOL
from tools.rag import (
    RAG_CHUNK_TOOL,
    RAG_CITATIONS_TOOL,
    RAG_RETRIEVE_TOOL,
    RAG_STORE_TOOL,
)
from tools.reporting import SPECIES_MODEL_OPINIONS_TOOL, SPECIES_REPORT_SYNTHESIS_TOOL
from tools.sequence import SEQUENCE_ANALYZE_TOOL
from tools.protein_structure import PROTEIN_STRUCTURE_ANALYZE_TOOL
from tools.web import TRUSTED_WEB_COLLECT_TOOL


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    tool.name: tool
    for tool in [
        ECHO_TOOL,
        ASK_USER_TOOL,
        NCBI_FETCH_TOOL,
        PDB_DOWNLOAD_TOOL,
        BIO_DATABASE_SEARCH_TOOL,
        SEQUENCE_ANALYZE_TOOL,
        GENOME_MAP_TOOL,
        PROTEIN_STRUCTURE_ANALYZE_TOOL,
        BLAST_SEARCH_TOOL,
        FILE_INSPECT_TOOL,
        PIPELINE_RUNNER_TOOL,
        PIPELINE_RESULTS_COLLECT_TOOL,
        PUBMED_COLLECT_TOOL,
        TRUSTED_WEB_COLLECT_TOOL,
        RAG_CHUNK_TOOL,
        RAG_STORE_TOOL,
        RAG_RETRIEVE_TOOL,
        RAG_CITATIONS_TOOL,
        SPECIES_MODEL_OPINIONS_TOOL,
        SPECIES_REPORT_SYNTHESIS_TOOL,
        MARKDOWN_REPORT_WRITER_TOOL,
    ]
}


def get_tool(name: str) -> ToolDefinition:
    try:
        return TOOL_REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(TOOL_REGISTRY))
        raise KeyError(f"Unknown tool '{name}'. Available tools: {available}") from exc


def list_tool_names() -> list[str]:
    return sorted(TOOL_REGISTRY)
