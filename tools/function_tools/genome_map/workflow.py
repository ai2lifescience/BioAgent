"""Genome map tool workflow."""
from __future__ import annotations
from tools.function_tools.genome_map.mapping import create_genome_map as _action_genome_map
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context
from tools.workspace import select_workspace_file

def genome_map(fasta_path: str | None=None, genbank_path: str | None=None, gff_path: str | None=None, artifact_ref: str | None=None, layout: str='circular', label: str | None=None, min_orf_length: int=90, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'genome_map')
    source_artifact = None
    if _should_use_latest_fasta(fasta_path=fasta_path, genbank_path=genbank_path, artifact_ref=artifact_ref):
        source_artifact = context.latest_file(kinds=('fasta',), suffixes=('.fasta', '.fa', '.fna', '.faa'))
        if not source_artifact:
            raise ValueError('No FASTA artifact is available in this session. Download or provide a FASTA/GenBank file path first.')
        fasta_path = str(source_artifact['path'])
    elif fasta_path:
        source, _display_path = select_workspace_file(
            context,
            fasta_path,
            suffixes=('.fasta', '.fa', '.fna', '.faa'),
        )
        fasta_path = str(source)
    if genbank_path:
        source, _display_path = select_workspace_file(
            context,
            genbank_path,
            suffixes=('.gb', '.gbk', '.genbank'),
        )
        genbank_path = str(source)
    if gff_path:
        source, _display_path = select_workspace_file(context, gff_path, suffixes=('.gff', '.gff3'))
        gff_path = str(source)
    result = context.call('genome_map', _action_genome_map, {'fasta_path': fasta_path, 'genbank_path': genbank_path, 'gff_path': gff_path, 'output_dir': context.workspace_path('genome_maps'), 'label': label, 'layout': layout, 'min_orf_length': min_orf_length})['result']
    lines = ['Genome map created.', f"Label: {result.get('label')}", f"Layout: {result.get('layout')}", f"Genome length: {result.get('genome_length')} bp", f"Features: {result.get('feature_count', 0)}", f"Genes: {result.get('gene_count', 0)}", f"CDS: {result.get('cds_count', 0)}", f"ORFs: {result.get('orf_count', 0)}", f"Image: {result.get('image_path')}"]
    return {'workflow': 'genome_map', 'tool': 'genome_map', 'answer': '\n'.join(lines), 'source_artifact': source_artifact, **result}

def _should_use_latest_fasta(fasta_path: str | None, genbank_path: str | None, artifact_ref: str | None) -> bool:
    if fasta_path or genbank_path:
        return False
    if artifact_ref == 'latest_fasta':
        return True
    return True
