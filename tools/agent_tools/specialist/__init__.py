"""Focused specialist agents exposed through the root Agent."""

from .coding import build_coding
from .data_analysis import build_data_analysis
from .document import build_document
from .pipeline import build_pipeline
from .retrieval import build_retrieval
from .biology import build_biology
from .web_research import build_web_research

# Compatibility aliases keep existing application imports stable while the
# canonical module and builder names remain short and domain-focused.
build_coding_specialist = build_coding
build_data_analysis_specialist = build_data_analysis
build_document_specialist = build_document
build_pipeline_specialist = build_pipeline
build_retrieval_specialist = build_retrieval
build_biology_specialist = build_biology
build_web_research_specialist = build_web_research

__all__ = [
    "build_coding_specialist",
    "build_data_analysis_specialist",
    "build_document_specialist",
    "build_pipeline_specialist",
    "build_retrieval_specialist",
    "build_biology_specialist",
    "build_web_research_specialist",
    "build_coding",
    "build_data_analysis",
    "build_document",
    "build_pipeline",
    "build_retrieval",
    "build_biology",
    "build_web_research",
]
