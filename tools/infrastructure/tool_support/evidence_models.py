"""Stable evidence artifact contracts shared across atomic and model tools."""
from __future__ import annotations

from typing import Literal

from .results import FunctionContract


class EvidenceRecord(FunctionContract):
    """One bounded source record persisted by search and retrieval tools."""

    id: str
    title: str
    url: str
    source: str
    text: str
    pmid: str | None = None
    year: str | None = None
    retrieved_at: str


class EvidenceArtifact(FunctionContract):
    """Workspace artifact format passed between evidence tools and report agents."""

    schema_version: Literal[1]
    sources: list[EvidenceRecord]


__all__ = ["EvidenceArtifact", "EvidenceRecord"]
