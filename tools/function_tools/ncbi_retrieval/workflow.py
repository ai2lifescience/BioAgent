"""NCBI retrieval tool workflow."""
from __future__ import annotations
from tools.function_tools.ncbi_retrieval.entrez.service import fetch_ncbi as _action_ncbi_fetch
from pathlib import Path
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context
from tools.function_tools.ncbi_retrieval.entrez import format_ncbi_result
from tools.function_tools.ncbi_retrieval.entrez.spec import DEFAULT_OUTPUT_DIR_PREFIX, DEFAULT_OUTPUT_DIR_TEMPLATE

def ncbi_retrieval(context: WorkflowContext | None=None, **kwargs: Any) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'ncbi_retrieval')
    output_dir = kwargs.get('output_dir')
    if _is_default_output_dir(output_dir):
        output_name = Path(str(output_dir or DEFAULT_OUTPUT_DIR_PREFIX)).name
        kwargs['output_dir'] = context.workspace_path('downloads', output_name)
    result = context.call('ncbi_fetch', _action_ncbi_fetch, kwargs)['result']
    answer = format_ncbi_result(result=result, fetch_args=kwargs)
    return {'skill': 'ncbi_retrieval', 'tool': 'ncbi_fetch', 'answer': answer, **result}

def _is_default_output_dir(output_dir: Any) -> bool:
    if not output_dir:
        return True
    value = str(output_dir)
    return value in {DEFAULT_OUTPUT_DIR_PREFIX, DEFAULT_OUTPUT_DIR_TEMPLATE} or value.startswith(f'{DEFAULT_OUTPUT_DIR_PREFIX}_')
