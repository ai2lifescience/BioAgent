"""Typed contracts for evidence-bound reporting agents."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from tools.infrastructure.tool_support.results import FunctionContract


class ReportInput(FunctionContract):
    question: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence_paths: Annotated[list[str], Field(min_length=1, max_length=10)]


class ReviewInput(ReportInput):
    """Input for evidence assessment."""


class SynthesisInput(ReportInput):
    """Input for cited report drafting."""


class ReviewResult(FunctionContract):
    assessment: str = Field(min_length=1, max_length=100_000)
    source_ids: list[str]
    limitations: list[str]


class ReportDraft(FunctionContract):
    markdown: str = Field(min_length=1, max_length=200_000)
    source_ids: list[str]
    limitations: list[str]


__all__ = [
    "ReportDraft",
    "ReportInput",
    "ReviewInput",
    "ReviewResult",
    "SynthesisInput",
]
