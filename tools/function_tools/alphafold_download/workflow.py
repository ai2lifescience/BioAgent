"""AlphaFold Database structure download workflow."""

from __future__ import annotations

from typing import Any

from tools.infrastructure.tooling.context import WorkflowContext, ensure_workflow_context
from tools.infrastructure.workspace import workspace_output_dir
from .client import download_alphafold_structure


def alphafold_download(
    accession: str,
    file_format: str = "cif",
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    context = ensure_workflow_context(context, "alphafold_download")
    result = context.call(
        "alphafold_download",
        download_alphafold_structure,
        {
            "accession": accession,
            "output_dir": str(workspace_output_dir(context, None, "alphafold")),
            "file_format": file_format,
        },
    )["result"]
    artifact = result["files"][0]
    return {
        "workflow": "alphafold_download",
        "tool": "alphafold_download",
        "accession": result.get("query", accession),
        "file_format": file_format,
        "structure_path": artifact.get("path"),
        "files": result.get("files", []),
        "record_count": result.get("record_count", 0),
        "provenance": result.get("provenance", {}),
        "summary": f"Downloaded AlphaFold {result.get('query', accession)} as {file_format.upper()}.",
    }


__all__ = ["alphafold_download"]
