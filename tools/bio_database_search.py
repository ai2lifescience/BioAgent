"""Workflow for querying UniProt, InterPro, KEGG, QuickGO, PDB, and AlphaFold DB for proteins, functions, pathways, ontology annotations, and structures."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.bio_database_search import database_lookup as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def database_lookup(
    ctx: RunContextWrapper[BioRunContext],
    database: Literal['uniprot', 'interpro', 'kegg', 'quickgo', 'pdb', 'alphafold'],
    query: str,
    max_results: Annotated[int, Field(ge=1, le=25)] = 5,
    operation: str | None = None,
    taxid: Annotated[int | None, Field(ge=1)] = None,
    download: bool = False,
    file_format: Literal['cif', 'pdb'] = 'cif',
    output_dir: str | None = None,
) -> str:
    """Workflow for querying UniProt, InterPro, KEGG, QuickGO, PDB, and AlphaFold DB for proteins, functions, pathways, ontology annotations, and structures."""
    return await run_workflow(ctx.context, 'database_lookup', _workflow,
        {'database': database, 'query': query, 'max_results': max_results, 'operation': operation, 'taxid': taxid, 'download': download, 'file_format': file_format, 'output_dir': output_dir}, category='bio_api',
        with_progress=False)
