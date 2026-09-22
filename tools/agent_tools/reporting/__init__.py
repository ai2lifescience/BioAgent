"""Composable, evidence-bound reporting agents."""

from .contracts import ReportDraft, ReviewInput, ReviewResult, SynthesisInput
from .review import build_report_review
from .synthesize import build_report_synthesize

__all__ = [
    "ReportDraft",
    "ReviewInput",
    "ReviewResult",
    "SynthesisInput",
    "build_report_review",
    "build_report_synthesize",
]
