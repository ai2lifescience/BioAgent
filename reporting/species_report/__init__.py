"""Species report prompt and synthesis services."""

from .opinions import collect_species_model_opinions
from .synthesis import synthesize_species_markdown_report

__all__ = [
    "collect_species_model_opinions",
    "synthesize_species_markdown_report",
]

