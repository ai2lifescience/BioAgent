"""Search one biological database for annotations and metadata."""
from __future__ import annotations

from typing import Any, Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from tools.infrastructure.providers.database.service import search_bio_database_tool
from tools.infrastructure.tool_support.artifacts import output

class LookupResult(FunctionContract):
    database: str
    query: str
    operation: str | None = None
    record_count: int
    records: list[dict[str, Any]]
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def _operation(*, database, query, max_results, operation, taxid, context):
    result = search_bio_database_tool(database, query, max_results, operation, taxid)
    # Metadata lookup has no file-writing side effect.
    result.pop("files", None)
    return output(result)


@bio_function_tool()
async def database_lookup(
    ctx: RunContextWrapper[AgentRunContext],
    database: Annotated[Literal["uniprot", "interpro", "kegg", "quickgo", "pdb", "alphafold"], Field(description="Database source for metadata.")],
    query: Annotated[str, Field(description="Database identifier, accession, protein name, pathway, ontology term, or structure ID.")],
    max_results: Annotated[int, Field(ge=1, le=25)] = 5,
    operation: Annotated[str | None, Field(description="Source-specific metadata operation; leave null for the source default.")] = None,
    taxid: Annotated[int | None, Field(ge=1)] = None,
) -> FunctionResult[LookupResult]:
    """Search UniProt, InterPro, KEGG, QuickGO, PDB, or AlphaFold metadata."""
    return await invoke(ctx.context, "database_lookup", _operation,
                              {"database": database, "query": query, "max_results": max_results,
                               "operation": operation, "taxid": taxid}, FunctionResult[LookupResult])


__all__ = ["database_lookup"]
