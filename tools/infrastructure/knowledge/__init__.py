"""Durable knowledge ingestion and retrieval infrastructure.

The package is private implementation code.  Model-facing boundaries live in
``tools.function_tools.knowledge_*`` and return only typed public contracts.
"""

from .models import KnowledgePage, KnowledgeSearchHit, TERMINAL_JOB_STATUSES
from .service import KnowledgeService

# Kept as a compatibility name for applications that used the first local
# implementation. New code should depend on KnowledgeService.
KnowledgeJobStore = KnowledgeService

__all__ = ["KnowledgeService", "KnowledgeJobStore", "KnowledgePage", "KnowledgeSearchHit", "TERMINAL_JOB_STATUSES"]
