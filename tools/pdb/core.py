"""PDB concrete tool implementations."""

from __future__ import annotations

from typing import Any

from bio_data.pdb import download_pdb_structure


def download_pdb_structure_tool(
    pdb_id: str,
    file_format: str = "cif",
    output_dir: str = "runtime/pdb",
) -> dict[str, Any]:
    return download_pdb_structure(
        pdb_id=pdb_id,
        file_format=file_format,
        output_dir=output_dir,
    )
