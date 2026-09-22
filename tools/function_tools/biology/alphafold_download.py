"""Download one AlphaFold Database prediction structure."""
from __future__ import annotations

from typing import Any, Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from pathlib import Path
from tools.infrastructure.providers.alphafold.client import download_alphafold_structure
from tools.infrastructure.workspace import workspace_output_dir
from tools.infrastructure.tool_support.artifacts import artifact, output

class DownloadResult(FunctionContract):
    accession: str
    file_format: str
    structure_path: str
    record_count: int
    provenance: dict[str, Any]
    summary: str


def _operation(*, accession, file_format, context):
    directory = workspace_output_dir(context, None, "alphafold")
    result = download_alphafold_structure(accession, str(directory), file_format)
    file = artifact(context, Path(result["structure_path"]))
    return output({"accession": result["query"], "file_format": file_format,
                   "structure_path": file["path"], "record_count": result["record_count"],
                   "provenance": result["provenance"],
                   "summary": f"Downloaded AlphaFold {result['query']} as {file_format.upper()}."}, file)


@bio_function_tool()
async def alphafold_download(
    ctx: RunContextWrapper[AgentRunContext],
    accession: Annotated[str, Field(description="UniProt accession for the AlphaFold prediction, for example P0A7V8.")],
    file_format: Annotated[Literal["cif", "pdb"], Field(description="Structure format to save.")] = "cif",
) -> FunctionResult[DownloadResult]:
    """Download an AlphaFold structure file for one UniProt accession."""
    return await invoke(ctx.context, "alphafold_download", _operation,
                              {"accession": accession, "file_format": file_format}, FunctionResult[DownloadResult])


__all__ = ["alphafold_download"]
