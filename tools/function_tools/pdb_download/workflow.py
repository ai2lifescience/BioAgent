"""PDB structure download tool workflow."""
from __future__ import annotations
from tools.function_tools.pdb_download.client import download_pdb_structure as _action_pdb_download
from typing import Any
from tools.infrastructure.tool_support.context import WorkflowContext, ensure_workflow_context
from tools.infrastructure.workspace import workspace_output_dir

def pdb_download(pdb_id: str, file_format: str='cif', output_dir: str | None=None, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'pdb_download')
    resolved_output_dir = workspace_output_dir(context, output_dir, 'structures')
    result = context.call('pdb_download', _action_pdb_download, {'pdb_id': pdb_id, 'file_format': file_format, 'output_dir': str(resolved_output_dir)})['result']
    answer = f"PDB structure downloaded.\nPDB ID: {result.get('pdb_id', pdb_id)}\nFormat: {result.get('file_format', file_format)}\nPath: {result.get('structure_path')}\nSource: {result.get('url')}"
    return {'workflow': 'pdb_download', 'tool': 'pdb_download', 'answer': answer, 'summary': f"Downloaded PDB {result.get('pdb_id', pdb_id)} as {result.get('file_format', file_format)}.", **result}
