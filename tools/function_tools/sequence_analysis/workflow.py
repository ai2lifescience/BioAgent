"""Sequence analysis tool workflow."""
from __future__ import annotations
from tools.function_tools.sequence_analysis.analysis import analyze_sequence_text as _action_sequence_analyze
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context

def sequence_analysis(sequence: str | None=None, fasta_path: str | None=None, artifact_ref: str | None=None, min_orf_length: int=90, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'sequence_analysis')
    source_artifact = None
    if _should_use_latest_fasta(sequence=sequence, fasta_path=fasta_path, artifact_ref=artifact_ref):
        source_artifact = context.latest_file(kinds=('fasta',), suffixes=('.fasta', '.fa', '.fna', '.faa'))
        if not source_artifact:
            raise ValueError('No FASTA artifact is available in this session. Download or provide a FASTA file path first.')
        fasta_path = str(source_artifact['path'])
    result = context.call('sequence_analyze', _action_sequence_analyze, {'sequence': sequence, 'fasta_path': fasta_path, 'min_orf_length': min_orf_length})['result']
    lines = ['Sequence analysis completed.', f"Records: {result.get('record_count', 0)}", f"Total length: {result.get('total_length', 0)}"]
    for item in result.get('records', []):
        lines.append(f"- {item.get('id')}: length {item.get('length')}, type {item.get('type')}, GC {item.get('gc_content_percent')}")
        if item.get('orfs'):
            lines.append(f"  ORFs: {len(item['orfs'])}")
    return {'skill': 'sequence_analysis', 'tool': 'sequence_analyze', 'answer': '\n'.join(lines), 'summary': f"Analyzed {result['record_count']} record(s), {result['total_length']} total symbols.", 'source_artifact': source_artifact, **result}

def _should_use_latest_fasta(sequence: str | None, fasta_path: str | None, artifact_ref: str | None) -> bool:
    if sequence:
        return False
    if artifact_ref == 'latest_fasta':
        return True
    if not fasta_path:
        return True
    return fasta_path.lower() in {'latest', 'latest_fasta', 'last_fasta', 'downloaded_fasta'}
