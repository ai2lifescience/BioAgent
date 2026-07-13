"""RAG tool implementation facade.

Detailed implementations live in operation-specific modules:
``chunk.py``, ``store.py``, and ``answer.py``.
"""

from __future__ import annotations

from tools.rag.cite import rag_citations_tool
from tools.rag.chunk import rag_chunk_tool
from tools.rag.retrieve import rag_retrieve_tool
from tools.rag.store import rag_store_tool

__all__ = [
    "rag_chunk_tool",
    "rag_citations_tool",
    "rag_retrieve_tool",
    "rag_store_tool",
]
