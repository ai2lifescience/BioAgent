"""Example tool workflow."""
from __future__ import annotations
from tools.function_tools.example_tool.diagnostics import echo_tool as _action_echo
from typing import Any
from tools.common.context import WorkflowContext, ensure_workflow_context

def example_tool(message: str, tag: str | None=None, uppercase: bool=False, context: WorkflowContext | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'example_tool')
    result = context.call('echo', _action_echo, {'message': message, 'tag': tag, 'uppercase': uppercase})['result']
    answer = f"Example tool completed.\nStatus: {result.get('status', 'unknown')}\nTag: {result.get('tag', 'example')}\nEcho: {result.get('echo', '')}\nWord count: {result.get('word_count', 0)}"
    return {'workflow': 'example_tool', 'tool': 'echo', 'answer': answer, **result}
