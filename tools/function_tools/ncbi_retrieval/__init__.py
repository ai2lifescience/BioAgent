"""Retrieve public records from NCBI Entrez as FASTA files plus metadata.

Use for accession, gene, organism, nucleotide, or protein sequence retrieval
when the user wants source records or files. Do not use for
BLAST similarity searches or a trusted narrative report; use ``blast_search``
or ``species_report`` instead.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import ncbi_retrieval as _workflow
from harness.context import BioRunContext
from tools.common.results import run_workflow
from tools.common.tooling import bio_function_tool


@bio_function_tool()
async def ncbi_retrieval(
    ctx: RunContextWrapper[BioRunContext],
    term: Annotated[str | None, Field(description='NCBI Entrez query for the requested organism, gene, or sequence. Use accessions for known record IDs.')] = None,
    terms: Annotated[list[str] | None, Field(description='Multiple independent Entrez queries for a batch retrieval.')] = None,
    genes: Annotated[list[str] | None, Field(description='Gene names to retrieve for the organism specified in term.')] = None,
    accessions: Annotated[list[str] | None, Field(description='Explicit NCBI sequence accession IDs to download.')] = None,
    db: Annotated[str, Field(description='NCBI sequence database supporting FASTA retrieval, normally nucleotide or protein. This tool does not collect PubMed literature.')] = 'nucleotide',
    max_records: Annotated[int, Field(ge=1)] = 10,
    year: Annotated[int | None, Field(ge=1)] = None,
    year_start: Annotated[int | None, Field(ge=1)] = None,
    year_end: Annotated[int | None, Field(ge=1)] = None,
    date_field: Literal['PDAT', 'MDAT'] = 'PDAT',
    output_dir: str | None = None,
    filename: str | None = None,
    metadata_filename: str | None = None,
) -> str:
    """Retrieve NCBI Entrez records as FASTA and metadata files.

    Use for nucleotide or protein sequence downloads by organism, gene, or
    accession. Writes FASTA and metadata CSV files. Use blast_search for
    similarity, sequence_analysis for existing sequences, and species_report
    for cited literature synthesis. Do not use for PubMed article retrieval.
    """
    return await run_workflow(ctx.context, 'ncbi_retrieval', _workflow,
        {'term': term, 'terms': terms, 'genes': genes, 'accessions': accessions, 'db': db, 'max_records': max_records, 'year': year, 'year_start': year_start, 'year_end': year_end, 'date_field': date_field, 'output_dir': output_dir, 'filename': filename, 'metadata_filename': metadata_filename}, category='ncbi',
        with_progress=False)
