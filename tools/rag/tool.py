"""RAG concrete tool definitions."""

from __future__ import annotations

from tools.base import ToolDefinition
from rag import DEFAULT_CHROMA_PATH
from tools.rag.core import (
    rag_chunk_tool,
    rag_citations_tool,
    rag_retrieve_tool,
    rag_store_tool,
)


RAG_CHUNK_TOOL = ToolDefinition(
    name="rag_chunk",
    description="Chunk source records into RAG-ready text chunks.",
    handler=rag_chunk_tool,
    category="retrieval",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "records": {"type": "array", "items": {"type": "object"}},
            "chunk_chars": {"type": "integer", "default": 1200},
            "overlap": {"type": "integer", "default": 180},
        },
        "required": ["records"],
    },
)

RAG_STORE_TOOL = ToolDefinition(
    name="rag_store",
    description="Embed records and store them in a persistent Chroma collection.",
    handler=rag_store_tool,
    category="retrieval",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "records": {"type": "array", "items": {"type": "object"}},
            "collection_name": {"type": "string", "default": "species_kb"},
            "chroma_path": {"type": "string", "default": DEFAULT_CHROMA_PATH},
        },
        "required": ["records"],
    },
)

RAG_RETRIEVE_TOOL = ToolDefinition(
    name="rag_retrieve",
    description="Retrieve, rank, filter, and cite chunks from a RAG collection.",
    handler=rag_retrieve_tool,
    category="retrieval",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "collection_name": {"type": "string", "default": "species_kb"},
            "chroma_path": {"type": "string", "default": DEFAULT_CHROMA_PATH},
            "top_k": {"type": "integer", "default": 5},
            "metadata_filters": {"type": "object"},
            "include_keyword": {"type": "boolean", "default": True},
        },
        "required": ["question"],
    },
)

RAG_CITATIONS_TOOL = ToolDefinition(
    name="rag_citations",
    description="Build citations and an evidence context from retrieved RAG chunks.",
    handler=rag_citations_tool,
    category="retrieval",
    risk_level="low",
    input_schema={
        "type": "object",
        "properties": {
            "chunks": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["chunks"],
    },
)
