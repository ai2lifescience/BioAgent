"""Reporting tool implementation facade."""

from reporting.species_report import (
    collect_species_model_opinions,
    synthesize_species_markdown_report,
)

__all__ = [
    "collect_species_model_opinions",
    "synthesize_species_markdown_report",
]

