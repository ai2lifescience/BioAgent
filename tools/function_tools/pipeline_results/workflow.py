"""Explicit result collection workflow for completed pipeline runs."""
from __future__ import annotations
from tools.function_tools.pipeline_results.collector import collect_pipeline_results as _action_pipeline_results_collect
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context
METRIC_LABELS = (('sample_id', 'Sample'), ('reference_id', 'Reference'), ('input_read_count', 'Input reads'), ('passed_read_count', 'Reads passing QC'), ('read_retention_percent', 'Read retention (%)'), ('q30_base_percent', 'Q30 bases (%)'), ('reference_coverage_percent', 'Reference coverage (%)'), ('mean_retained_depth', 'Mean retained depth'), ('variant_count', 'Passing variants'))

def _cell(value: Any) -> str:
    return str(value).replace('|', '\\|').replace('\n', ' ')

def _markdown_table(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    if not columns:
        return ['No columns were found.']
    lines = ['| ' + ' | '.join((_cell(column) for column in columns)) + ' |', '| ' + ' | '.join(('---' for _column in columns)) + ' |']
    for row in rows:
        lines.append('| ' + ' | '.join((_cell(row.get(column, '')) for column in columns)) + ' |')
    return lines

def _answer(result: dict[str, Any]) -> str:
    if result.get('status') != 'ok':
        requested = result.get('pipeline_name') or 'the requested pipeline'
        return f'No completed outputs for {requested} are available in this chat session. Run the pipeline first, then request the results again.'
    metrics = result.get('metrics') or {}
    lines = [f"# Collected {result.get('pipeline_name', 'pipeline')} results", '', f"Collected {result.get('output_count', 0)} output files from the latest completed run.", f"A ZIP bundle is available as `{str(result.get('bundle_path') or '').split('/')[-1]}`.", '', '## Key metrics', '', '| Metric | Value |', '| --- | ---: |']
    metric_rows = 0
    for key, label in METRIC_LABELS:
        if key not in metrics:
            continue
        lines.append(f'| {_cell(label)} | {_cell(metrics[key])} |')
        metric_rows += 1
    if not metric_rows:
        lines.append('| Metrics | Not available |')
    for table in result.get('tables') or []:
        lines.extend(['', f"## {table.get('name', 'Table')}", ''])
        lines.extend(_markdown_table(table.get('columns') or [], table.get('rows') or []))
        if table.get('truncated'):
            lines.extend(['', f"Showing {len(table.get('rows') or [])} of {table.get('row_count', 0)} rows."])
    lines.extend(['', '## Output manifest', ''])
    for output in result.get('outputs') or []:
        lines.append(f"- `{_cell(output.get('name', 'output'))}` — {_cell(output.get('kind', 'file'))}, {output.get('bytes', 0)} bytes")
    if result.get('image_paths'):
        lines.extend(['', 'The result figures are displayed below this summary.'])
    return '\n'.join(lines)

def pipeline_results(pipeline_name: str='', max_table_rows: int=10, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'pipeline_results')
    result = context.call('pipeline_results_collect', _action_pipeline_results_collect, {'files': context.files, 'collection_dir': context.workspace_path('pipeline-results', context.run_id or 'latest'), 'pipeline_name': pipeline_name, 'max_table_rows': max_table_rows})['result']
    return {'skill': 'pipeline_results', 'tool': 'pipeline_results_collect', 'answer': _answer(result), 'presentation': 'expanded_results', **result}
