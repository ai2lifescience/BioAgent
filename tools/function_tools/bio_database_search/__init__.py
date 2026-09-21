"""Search one biological database for annotations, pathways, ontology terms, or structure metadata.

Use for UniProt, InterPro, KEGG, QuickGO, PDB metadata, and AlphaFold DB
metadata. Use ``pdb_download`` or ``alphafold_download`` when the user wants
a structure file. Do not use this tool for NCBI retrieval, BLAST similarity,
local structure analysis, or a narrative species report.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import database_lookup as _workflow
from harness.context import AgentRunContext
from tools.infrastructure.tool_support.results import run_workflow
from tools.infrastructure.tool_support.decorators import bio_function_tool


@bio_function_tool()
async def database_lookup(
    ctx: RunContextWrapper[AgentRunContext],
    database: Annotated[Literal['uniprot', 'interpro', 'kegg', 'quickgo', 'pdb', 'alphafold'], Field(description='Database source for metadata. Use pdb_download or alphafold_download for structure files.')],
    query: Annotated[str, Field(description='Database identifier, accession, protein name, pathway, ontology term, or structure ID to search.')],
    max_results: Annotated[int, Field(ge=1, le=25)] = 5,
    operation: Annotated[str | None, Field(description='Source-specific metadata operation; leave null for the source default. Examples: InterPro protein_domains; KEGG get, find, or link; QuickGO annotation_search or term_details; PDB entry_details or search.')] = None,
    taxid: Annotated[int | None, Field(ge=1)] = None,
) -> str:
    """Search one biological database for annotations, pathways, ontology terms, or structure metadata.

    Use UniProt, InterPro, KEGG, QuickGO, PDB, or AlphaFold DB for protein
    annotations, pathways, ontology terms, and metadata. Use pdb_download or
    alphafold_download for structure files, protein_structure_analysis for
    local structure analysis, ncbi_retrieval for sequence records, and
    species_report for cited reports.
    """
    return await run_workflow(ctx.context, 'database_lookup', _workflow,
        {'database': database, 'query': query, 'max_results': max_results, 'operation': operation, 'taxid': taxid}, category='database',
        with_progress=False)
