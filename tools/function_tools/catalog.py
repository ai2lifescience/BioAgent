"""Explicit model-facing FunctionTool catalog."""

from .sequence_stats import sequence_stats
from .sequence_find_orfs import sequence_find_orfs
from .sequence_translate import sequence_translate
from .sequence_reverse_complement import sequence_reverse_complement
from .table_profile import table_profile
from .table_group import table_group
from .table_plot import table_plot
from .structure_inspect import structure_inspect
from .genome_read_features import genome_read_features
from .genome_render_map import genome_render_map
from .pubmed_search import pubmed_search
from .web_search import web_search
from .web_fetch import web_fetch
from .evidence_index import evidence_index
from .evidence_retrieve import evidence_retrieve
from .report_write import report_write

from .alphafold_download import alphafold_download
from .ncbi_retrieval import ncbi_retrieval
from .database_lookup import database_lookup
from .pdb_download import pdb_download
from .blast_search import blast_search
from .file_inspection import file_inspection
from .document_read import document_read
from .workspace_search import workspace_search
from .code_inspection import code_inspection
from .code_edit import code_edit
from .code_test import code_test


FUNCTION_TOOLS = [
    sequence_stats, sequence_find_orfs, sequence_translate, sequence_reverse_complement,
    table_profile, table_group, table_plot, structure_inspect,
    genome_read_features, genome_render_map, pubmed_search, web_search, web_fetch,
    evidence_index, evidence_retrieve, report_write,
    alphafold_download, ncbi_retrieval, database_lookup, pdb_download, blast_search,
    file_inspection, document_read, workspace_search, code_inspection, code_edit, code_test,
]



__all__ = [
    "FUNCTION_TOOLS",
    "sequence_stats",
    "sequence_find_orfs",
    "sequence_translate",
    "sequence_reverse_complement",
    "table_profile",
    "table_group",
    "table_plot",
    "structure_inspect",
    "genome_read_features",
    "genome_render_map",
    "pubmed_search",
    "web_search",
    "web_fetch",
    "evidence_index",
    "evidence_retrieve",
    "report_write",
    "alphafold_download",
    "ncbi_retrieval",
    "database_lookup",
    "pdb_download",
    "blast_search",
    "file_inspection",
    "document_read",
    "workspace_search",
    "code_inspection",
    "code_edit",
    "code_test",
]
