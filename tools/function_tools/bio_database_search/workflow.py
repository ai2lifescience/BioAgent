"""Biological database lookup tool workflow."""
from __future__ import annotations
from tools.function_tools.bio_database_search.service import search_bio_database_tool as _action_bio_database_search
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context

def database_lookup(database: str, query: str, max_results: int=5, operation: str | None=None, taxid: int | None=None, download: bool=False, file_format: str='cif', output_dir: str | None=None, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'database_lookup')
    payload: dict[str, Any] = {'database': database, 'query': query, 'max_results': max_results, 'download': download, 'file_format': file_format}
    if operation:
        payload['operation'] = operation
    if taxid is not None:
        payload['taxid'] = taxid
    if output_dir:
        payload['output_dir'] = output_dir
    result = context.call('bio_database_search', _action_bio_database_search, payload)['result']
    lines = [f"{result.get('database', 'database')} search completed.", f"Query: {result.get('query', query)}", f"Records returned: {result.get('record_count', 0)}"]
    for item in result.get('records', [])[:10]:
        record_id = item.get('accession') or item.get('entry_id') or item.get('entry') or item.get('identifier') or item.get('id')
        label = item.get('name') or item.get('protein_name') or item.get('title') or item.get('definition') or item.get('value') or item.get('organism') or ''
        url = item.get('url') or ''
        lines.append(f'- {record_id}: {label} {url}'.strip())
    return {'skill': 'database_lookup', 'tool': 'bio_database_search', 'answer': '\n'.join(lines), **result}
