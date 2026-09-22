"""Canonical model-facing FunctionTools grouped by capability family.

The family lists are organizational views. ``FUNCTION_TOOLS`` is the single
flattened list passed to the Agents SDK root agent.
"""

from .biology.sequence_stats import sequence_stats
from .biology.sequence_find_orfs import sequence_find_orfs
from .biology.sequence_translate import sequence_translate
from .biology.sequence_reverse_complement import sequence_reverse_complement
from .data_analysis.table_profile import table_profile
from .data_analysis.table_group import table_group
from .data_analysis.table_plot import table_plot
from .biology.structure_inspect import structure_inspect
from .biology.genome_read_features import genome_read_features
from .biology.genome_render_map import genome_render_map
from .sources.pubmed_search import pubmed_search
from .sources.web_search import web_search
from .sources.web_fetch import web_fetch
from .knowledge.evidence_index import evidence_index
from .knowledge.evidence_retrieve import evidence_retrieve
from .knowledge.knowledge_ingest import knowledge_ingest
from .knowledge.knowledge_status import knowledge_status
from .knowledge.knowledge_retrieve import knowledge_retrieve
from .workspace.report_write import report_write

from .biology.alphafold_download import alphafold_download
from .biology.ncbi_retrieval import ncbi_retrieval
from .biology.database_lookup import database_lookup
from .biology.pdb_download import pdb_download
from .biology.blast_search import blast_search
from .workspace.file_inspection import file_inspection
from .workspace.document_read import document_read
from .workspace.workspace_search import workspace_search
from .coding.code_inspection import code_inspection
from .coding.code_edit import code_edit
from .coding.code_test import code_test


BIOLOGY_TOOLS = [
    sequence_stats, sequence_find_orfs, sequence_translate, sequence_reverse_complement,
    alphafold_download, ncbi_retrieval, database_lookup, pdb_download, blast_search,
    structure_inspect, genome_read_features, genome_render_map,
]

DATA_ANALYSIS_TOOLS = [table_profile, table_group, table_plot]

SOURCE_TOOLS = [pubmed_search, web_search, web_fetch]

KNOWLEDGE_TOOLS = [
    evidence_index, evidence_retrieve, knowledge_ingest, knowledge_status, knowledge_retrieve,
]

WORKSPACE_TOOLS = [file_inspection, document_read, workspace_search, report_write]

CODING_TOOLS = [code_inspection, code_edit, code_test]

FUNCTION_TOOL_GROUPS = {
    "biology": BIOLOGY_TOOLS,
    "data_analysis": DATA_ANALYSIS_TOOLS,
    "sources": SOURCE_TOOLS,
    "knowledge": KNOWLEDGE_TOOLS,
    "workspace": WORKSPACE_TOOLS,
    "coding": CODING_TOOLS,
}

FUNCTION_TOOLS = [
    tool
    for group in FUNCTION_TOOL_GROUPS.values()
    for tool in group
]


__all__ = ["FUNCTION_TOOLS"]
