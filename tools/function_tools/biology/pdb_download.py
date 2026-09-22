"""Download one structure file from RCSB PDB."""
from __future__ import annotations

from typing import Annotated, Literal

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


from pathlib import Path
from tools.infrastructure.providers.pdb.client import download_pdb_structure
from tools.infrastructure.workspace import workspace_output_dir
from tools.infrastructure.tool_support.artifacts import artifact, output

class DownloadResult(FunctionContract):
    database: str
    pdb_id: str
    identifier: str
    file_format: str
    url: str
    structure_path: str
    output_dir: str
    bytes: int
    summary: str


def _operation(*, pdb_id, file_format="cif", output_dir=None, context):
    if output_dir is not None and Path(output_dir).is_absolute():
        raise ValueError("output_dir must be workspace-relative.")
    directory = workspace_output_dir(context, output_dir, "structures")
    result = download_pdb_structure(pdb_id, file_format, str(directory))
    result.pop("status")
    file = artifact(context, Path(result["structure_path"]))
    result["structure_path"] = file["path"]
    result["summary"] = f"Downloaded PDB {result['pdb_id']} as {result['file_format'].upper()}."
    return output(result, file)


@bio_function_tool()
async def pdb_download(
    ctx: RunContextWrapper[AgentRunContext],
    pdb_id: Annotated[str, Field(description="Four-character PDB ID, for example 1A3N.")],
    file_format: Annotated[Literal["cif", "pdb", "bcif"], Field(description="Structure file format.")] = "cif",
    output_dir: Annotated[str | None, Field(description="Session-relative output directory.")] = None,
) -> FunctionResult[DownloadResult]:
    """Download one RCSB PDB structure file."""
    return await invoke(ctx.context, "pdb_download", _operation,
                              {"pdb_id": pdb_id, "file_format": file_format, "output_dir": output_dir}, FunctionResult[DownloadResult])


__all__ = ["pdb_download"]
