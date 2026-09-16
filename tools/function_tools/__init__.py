"""Agent-facing OpenAI Agents SDK FunctionTool definitions."""

from .example_skill import example_skill
from .species_report import species_report
from .ncbi_retrieval import ncbi_retrieval
from .bio_database_search import database_lookup
from .pdb_download import pdb_download
from .sequence_analysis import sequence_analysis
from .genome_map import genome_map
from .protein_structure_analysis import protein_structure_analysis
from .blast_search import blast_search
from .file_inspection import file_inspection

FUNCTION_TOOLS = [
    example_skill,
    species_report,
    ncbi_retrieval,
    database_lookup,
    pdb_download,
    sequence_analysis,
    genome_map,
    protein_structure_analysis,
    blast_search,
    file_inspection,
]

__all__ = [
    "FUNCTION_TOOLS",
    "example_skill",
    "species_report",
    "ncbi_retrieval",
    "database_lookup",
    "pdb_download",
    "sequence_analysis",
    "genome_map",
    "protein_structure_analysis",
    "blast_search",
    "file_inspection",
]
