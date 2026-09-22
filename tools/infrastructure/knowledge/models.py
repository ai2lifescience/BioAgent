"""Domain contracts for durable knowledge ingestion and retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from tools.infrastructure.tool_support.evidence_models import EvidenceRecord


TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled", "interrupted"})


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex}"


def source_id(collection_id: str, url: str) -> str:
    return "src_" + hashlib.sha256((collection_id + "\n" + url).encode("utf-8")).hexdigest()[:24]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KnowledgePage:
    """Normalized document returned by a crawler."""

    url: str
    title: str
    text: str
    depth: int = 0


@dataclass(frozen=True)
class KnowledgeSearchHit:
    """One chunk selected by hybrid retrieval."""

    score: float
    record: EvidenceRecord


__all__ = ["KnowledgePage", "KnowledgeSearchHit", "TERMINAL_JOB_STATUSES", "content_hash", "new_id", "now", "source_id"]
