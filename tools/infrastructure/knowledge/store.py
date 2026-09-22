"""Compatibility facade for the pre-refactor knowledge store.

The implementation now lives in ``service``, ``repository``, ``indexer``,
``jobs``, and ``crawlers``. This module remains import-safe for integrations
that used the old private path during the transition.
"""
from .models import KnowledgePage, KnowledgeSearchHit, TERMINAL_JOB_STATUSES
from .service import KnowledgeService

KnowledgeJobStore = KnowledgeService

__all__ = ["KnowledgeJobStore", "KnowledgePage", "KnowledgeSearchHit", "TERMINAL_JOB_STATUSES"]
