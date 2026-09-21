"""Download one specific structure file from RCSB PDB.

Use when the user asks to fetch, save, or download a PDB structure. Do not use
to analyze an existing structure; use ``protein_structure_analysis`` instead.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from agents import RunContextWrapper
from pydantic import Field

from .workflow import pdb_download as _workflow
from harness.context import AgentRunContext
from tools.infrastructure.tooling.results import run_workflow
from tools.infrastructure.tooling.tooling import bio_function_tool


@bio_function_tool()
async def pdb_download(
    ctx: RunContextWrapper[AgentRunContext],
    pdb_id: Annotated[str, Field(description='Four-character PDB ID, for example 1A3N.')],
    file_format: Annotated[Literal['cif', 'pdb', 'bcif'], Field(description='Structure file format to download.')] = 'cif',
    output_dir: Annotated[str | None, Field(description='Session-relative output directory; defaults to outputs/structures. Paths outside the session are rejected.')] = None,
) -> str:
    """Download one RCSB PDB structure file in the requested format.

    Use for fetch, save, or download requests for a specific PDB ID in mmCIF,
    PDB, or BinaryCIF format. Writes a local structure file. Use
    database_lookup for remote PDB metadata or search and
    protein_structure_analysis when the goal is analyzing a structure.
    """
    return await run_workflow(ctx.context, 'pdb_download', _workflow,
        {'pdb_id': pdb_id, 'file_format': file_format, 'output_dir': output_dir}, category='pdb',
        with_progress=False)
