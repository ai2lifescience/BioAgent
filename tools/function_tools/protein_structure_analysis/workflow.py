"""Protein structure analysis tool workflow."""
from __future__ import annotations
from tools.function_tools.protein_structure_analysis.analysis import analyze_protein_structure_file as _action_protein_structure_analyze
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context
from tools.workspace import select_workspace_file

def protein_structure_analysis(structure_path: str | None=None, artifact_ref: str | None=None, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'protein_structure_analysis')
    source_artifact = None
    if _should_use_latest_structure(structure_path=structure_path, artifact_ref=artifact_ref):
        source_artifact = context.latest_file(kinds=('structure',), suffixes=('.cif', '.mmcif', '.pdb'))
        if not source_artifact:
            raise ValueError('No structure artifact is available in this session. Use pdb_download first or provide a structure_path.')
        structure_path = str(source_artifact['path'])
        display_path = str(source_artifact.get('workspace_path') or source_artifact.get('path') or structure_path)
    elif structure_path:
        source, display_path = select_workspace_file(
            context,
            structure_path,
            suffixes=('.cif', '.mmcif', '.pdb'),
        )
        structure_path = str(source)
    if not structure_path:
        raise ValueError('structure_path or artifact_ref is required.')
    result = context.call('protein_structure_analyze', _action_protein_structure_analyze, {'structure_path': structure_path})['result']
    result['structure_path'] = display_path
    lines = ['Protein structure analysis completed.', f"Path: {result.get('structure_path')}", f"Format: {result.get('file_format')}", f"Atoms: {result.get('atom_count', 0)}", f"Chains: {result.get('chain_count', 0)} ({', '.join(result.get('chains', [])) or 'none'})", f"Residues: {result.get('residue_count', 0)}", f"Ligands: {', '.join(result.get('ligands', [])) or 'none'}", f"Water atoms: {result.get('water_count', 0)}"]
    if result.get('experimental_method'):
        lines.append(f"Method: {result['experimental_method']}")
    if result.get('resolution_angstrom') is not None:
        lines.append(f"Resolution: {result['resolution_angstrom']} A")
    return {'workflow': 'protein_structure_analysis', 'tool': 'protein_structure_analyze', 'answer': '\n'.join(lines), 'summary': result.get('summary'), 'source_artifact': source_artifact, **result}

def _should_use_latest_structure(structure_path: str | None, artifact_ref: str | None) -> bool:
    if artifact_ref == 'latest_structure':
        return True
    if not structure_path:
        return True
    return structure_path.lower() in {'latest', 'latest_structure', 'last_structure', 'downloaded_structure'}
