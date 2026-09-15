"""Protein structure analysis skill workflow."""
from __future__ import annotations
from biology.pdb.core import download_pdb_structure_tool as _action_pdb_download
from biology.protein_structure.core import analyze_protein_structure_file as _action_protein_structure_analyze
from typing import Any
from biology.context import WorkflowContext, ensure_workflow_context

def protein_structure_analysis(structure_path: str | None=None, pdb_id: str | None=None, file_format: str='cif', artifact_ref: str | None=None, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'protein_structure_analysis')
    source_artifact = None
    download_result = None
    if pdb_id and (not structure_path):
        download_result = context.call('pdb_download', _action_pdb_download, {'pdb_id': pdb_id, 'file_format': file_format or 'cif', 'output_dir': context.artifact_path('structures')})['result']
        structure_path = str(download_result['structure_path'])
    elif _should_use_latest_structure(structure_path=structure_path, artifact_ref=artifact_ref):
        source_artifact = context.latest_artifact(kinds=('structure',), suffixes=('.cif', '.mmcif', '.pdb'))
        if not source_artifact:
            raise ValueError('No structure artifact is available in this session. Download a PDB structure or provide a structure_path first.')
        structure_path = str(source_artifact['path'])
    if not structure_path:
        raise ValueError('structure_path, pdb_id, or artifact_ref is required.')
    result = context.call('protein_structure_analyze', _action_protein_structure_analyze, {'structure_path': structure_path})['result']
    lines = ['Protein structure analysis completed.', *([f"PDB ID: {download_result.get('pdb_id', pdb_id)}"] if download_result else []), f"Path: {result.get('structure_path')}", f"Format: {result.get('file_format')}", f"Atoms: {result.get('atom_count', 0)}", f"Chains: {result.get('chain_count', 0)} ({', '.join(result.get('chains', [])) or 'none'})", f"Residues: {result.get('residue_count', 0)}", f"Ligands: {', '.join(result.get('ligands', [])) or 'none'}", f"Water atoms: {result.get('water_count', 0)}"]
    if result.get('experimental_method'):
        lines.append(f"Method: {result['experimental_method']}")
    if result.get('resolution_angstrom') is not None:
        lines.append(f"Resolution: {result['resolution_angstrom']} A")
    return {'skill': 'protein_structure_analysis', 'tool': 'protein_structure_analyze', 'answer': '\n'.join(lines), 'summary': result.get('summary'), 'source_artifact': source_artifact, 'download': download_result, 'pdb_id': (download_result or {}).get('pdb_id', pdb_id), **result}

def _should_use_latest_structure(structure_path: str | None, artifact_ref: str | None) -> bool:
    if artifact_ref == 'latest_structure':
        return True
    if not structure_path:
        return True
    return structure_path.lower() in {'latest', 'latest_structure', 'last_structure', 'downloaded_structure'}
