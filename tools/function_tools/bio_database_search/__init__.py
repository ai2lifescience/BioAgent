"""Search one biological database for annotations, pathways, ontology terms, structure metadata, or AlphaFold records.

Use for UniProt, InterPro, KEGG, QuickGO, PDB metadata, and AlphaFold DB.
Use ``pdb_download`` when the user wants an RCSB PDB file. Do not use this
tool for NCBI retrieval, BLAST similarity, local structure analysis, or a
narrative species report.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from .workflow import database_lookup as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow, tool_error
from tools.common.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def database_lookup(
    ctx: RunContextWrapper[BioRunContext],
    database: Annotated[Literal['uniprot', 'interpro', 'kegg', 'quickgo', 'pdb', 'alphafold'], Field(description='Database source. Use pdb for structure metadata; use pdb_download for PDB file downloads.')],
    query: Annotated[str, Field(description='Database identifier, accession, protein name, pathway, ontology term, or structure ID to search.')],
    max_results: Annotated[int, Field(ge=1, le=25)] = 5,
    operation: Annotated[str | None, Field(description='Source-specific operation; leave null for the source default. Examples: InterPro protein_domains; KEGG get, find, or link; QuickGO annotation_search or term_details; PDB entry_details or search.')] = None,
    taxid: Annotated[int | None, Field(ge=1)] = None,
    download: Annotated[bool, Field(description='Download an AlphaFold record when supported. Use pdb_download for RCSB PDB files.')] = False,
    file_format: Annotated[Literal['cif', 'pdb'], Field(description='Structure format when downloading an AlphaFold model.')] = 'cif',
    output_dir: Annotated[str | None, Field(description='Optional destination directory for a requested AlphaFold model download.')] = None,
) -> str:
    """Search one biological database for annotations, pathways, ontology terms, structure metadata, or AlphaFold records.

    Use UniProt, InterPro, KEGG, QuickGO, PDB, or AlphaFold DB for protein
    annotations, pathways, ontology terms, and structure metadata. This tool
    also supports AlphaFold model downloads. Use pdb_download for RCSB PDB
    file downloads, protein_structure_analysis for local structure analysis,
    ncbi_retrieval for sequence records, and species_report for cited reports.
    """
    return await run_workflow(ctx.context, 'database_lookup', _workflow,
        {'database': database, 'query': query, 'max_results': max_results, 'operation': operation, 'taxid': taxid, 'download': download, 'file_format': file_format, 'output_dir': output_dir}, category='database',
        with_progress=False)
