"""Retrieve public NCBI Entrez sequence records and metadata."""
from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from pathlib import Path
from tools.infrastructure.providers.ncbi.entrez.service import fetch_ncbi
from tools.infrastructure.workspace import workspace_output_dir, output_file_path
from tools.infrastructure.tool_support.artifacts import artifact, output

class QueryResult(FunctionContract):
    term: str
    db: str
    sequence_format: str
    metadata_format: str
    matched_count: int
    downloaded_count: int
    output_dir: str
    output_path: str | None = None
    fasta_path: str | None = None
    metadata_path: str | None = None
    query_translation: str | None = None
    message: str | None = None
    bytes_written: int | None = None
    fasta_records: int | None = None
    metadata_records: int | None = None
    metadata_bytes_written: int | None = None
    label: str | None = None


class RetrievalResult(FunctionContract):
    db: str
    sequence_format: str
    metadata_format: str
    query_count: int
    matched_count: int
    downloaded_count: int
    output_dir: str
    results: list[QueryResult]
    fasta_paths: list[str]
    metadata_paths: list[str]


def _operation(*, context, **arguments):
    output_dir = arguments.get("output_dir")
    if output_dir is not None and Path(output_dir).is_absolute():
        raise ValueError("output_dir must be workspace-relative.")
    directory = workspace_output_dir(context, output_dir, "downloads", "ncbi")
    for key in ("filename", "metadata_filename"):
        if arguments.get(key):
            output_file_path(directory, arguments[key])
    arguments["output_dir"] = str(directory)
    result = fetch_ncbi(**arguments)
    files = [artifact(context, Path(path)) for path in dict.fromkeys(
        result["fasta_paths"] + result["metadata_paths"])]
    return output(result, *files)


@bio_function_tool()
async def ncbi_retrieval(
    ctx: RunContextWrapper[AgentRunContext],
    term: Annotated[str | None, Field(description="NCBI Entrez query for an organism, gene, or sequence.")] = None,
    terms: Annotated[list[str] | None, Field(description="Multiple independent Entrez queries.")] = None,
    genes: Annotated[list[str] | None, Field(description="Gene names for the organism in term.")] = None,
    accessions: Annotated[list[str] | None, Field(description="Explicit NCBI accession IDs.")] = None,
    db: Annotated[str, Field(description="NCBI sequence database, normally nucleotide or protein.")] = "nucleotide",
    max_records: Annotated[int, Field(ge=1)] = 10,
    year: Annotated[int | None, Field(ge=1)] = None,
    year_start: Annotated[int | None, Field(ge=1)] = None,
    year_end: Annotated[int | None, Field(ge=1)] = None,
    date_field: Literal["PDAT", "MDAT"] = "PDAT",
    output_dir: Annotated[str | None, Field(description="Session-relative output directory.")] = None,
    filename: Annotated[str | None, Field(description="Optional FASTA filename.")] = None,
    metadata_filename: Annotated[str | None, Field(description="Optional metadata filename.")] = None,
) -> FunctionResult[RetrievalResult]:
    """Retrieve NCBI Entrez records as FASTA and metadata files."""
    arguments = {"term": term, "terms": terms, "genes": genes, "accessions": accessions,
                 "db": db, "max_records": max_records, "year": year, "year_start": year_start,
                 "year_end": year_end, "date_field": date_field, "output_dir": output_dir,
                 "filename": filename, "metadata_filename": metadata_filename}
    return await invoke(ctx.context, "ncbi_retrieval", _operation, arguments, FunctionResult[RetrievalResult])


__all__ = ["ncbi_retrieval"]
