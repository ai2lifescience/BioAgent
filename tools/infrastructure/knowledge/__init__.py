"""Durable knowledge ingestion and retrieval infrastructure.

The package is private implementation code.  Model-facing boundaries live in
``tools.function_tools.knowledge_*`` and return only typed public contracts.
"""

from .store import KnowledgeJobStore, KnowledgePage, KnowledgeSearchHit

__all__ = ["KnowledgeJobStore", "KnowledgePage", "KnowledgeSearchHit"]
