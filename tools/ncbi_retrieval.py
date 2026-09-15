"""Workflow for searching NCBI Entrez and downloading public sequence records as FASTA plus metadata CSV files. Use for NCBI, Entrez, FASTA, nucleotide, protein, genome, gene, accession, or PubMed data retrieval requests."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper, function_tool
from pydantic import Field

from biology.workflows.ncbi_retrieval import ncbi_retrieval as _workflow
from harness.context import BioRunContext
from tools.results import run_workflow, tool_error
from tools.guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL


@function_tool(strict_mode=True, failure_error_function=tool_error, tool_input_guardrails=[TOOL_INPUT_GUARDRAIL], tool_output_guardrails=[TOOL_OUTPUT_GUARDRAIL], timeout=300)
async def ncbi_retrieval(
    ctx: RunContextWrapper[BioRunContext],
    term: str | None = None,
    terms: list[str] | None = None,
    genes: list[str] | None = None,
    accessions: list[str] | None = None,
    db: str = 'nucleotide',
    max_records: Annotated[int, Field(ge=1)] = 10,
    year: Annotated[int | None, Field(ge=1)] = None,
    year_start: Annotated[int | None, Field(ge=1)] = None,
    year_end: Annotated[int | None, Field(ge=1)] = None,
    date_field: Literal['PDAT', 'MDAT'] = 'PDAT',
    output_dir: str | None = None,
    filename: str | None = None,
    metadata_filename: str | None = None,
) -> str:
    """Workflow for searching NCBI Entrez and downloading public sequence records as FASTA plus metadata CSV files. Use for NCBI, Entrez, FASTA, nucleotide, protein, genome, gene, accession, or PubMed data retrieval requests."""
    return await run_workflow(ctx.context, 'ncbi_retrieval', _workflow,
        {'term': term, 'terms': terms, 'genes': genes, 'accessions': accessions, 'db': db, 'max_records': max_records, 'year': year, 'year_start': year_start, 'year_end': year_end, 'date_field': date_field, 'output_dir': output_dir, 'filename': filename, 'metadata_filename': metadata_filename}, category='bio_data',
        with_progress=False)
