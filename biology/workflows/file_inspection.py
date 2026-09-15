"""File inspection skill workflow."""
from __future__ import annotations
from biology.file_io.core import inspect_bio_file as _action_file_inspect
from typing import Any
from biology.context import WorkflowContext, ensure_workflow_context

def file_inspection(path: str, max_preview_lines: int=20, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'file_inspection')
    result = context.call('file_inspect', _action_file_inspect, {'path': path, 'max_preview_lines': max_preview_lines})['result']
    answer = f"File inspection completed.\nPath: {result.get('path')}\nType: {result.get('file_type')}\nLines: {result.get('line_count')}\nBytes: {result.get('bytes')}\nRecords/rows: {result.get('record_count', result.get('row_count', 'n/a'))}"
    return {'skill': 'file_inspection', 'tool': 'file_inspect', 'answer': answer, 'summary': f"Inspected {result['file_type']} file with {result.get('record_count', result.get('row_count', result['line_count']))} item(s).", **result}
