"""Ordered deterministic route rules for BioAgent.

Route rules parse common requests into exact skill calls. Model-facing skill
semantics live in the registered skill specs, not in this module.
"""

from __future__ import annotations

from collections.abc import Callable

from agent_core.router import IntentRoute

from .comparison import route_comparison_research
from .database import route_bio_database, route_pdb_download
from .diagnostics import route_example_skill
from .file_io import route_file_inspection
from .general import route_control_response, route_llm_response
from .genome import route_genome_map
from .literature import route_literature_evidence_review
from .ncbi import route_ncbi
from .pipeline import route_pipeline
from .pipeline_results import route_pipeline_results
from .sequence import route_blast, route_sequence_analysis
from .species import route_species_report
from .protein_structure import route_protein_structure_analysis


RouteRule = Callable[[str], IntentRoute | None]

ROUTE_RULES: tuple[RouteRule, ...] = (
    route_control_response,
    route_ncbi,
    route_example_skill,
    route_pipeline_results,
    route_pipeline,
    route_genome_map,
    route_protein_structure_analysis,
    route_file_inspection,
    route_blast,
    route_sequence_analysis,
    route_pdb_download,
    route_bio_database,
    route_literature_evidence_review,
    route_comparison_research,
    route_species_report,
    route_llm_response,
)


__all__ = ["ROUTE_RULES", "RouteRule"]
