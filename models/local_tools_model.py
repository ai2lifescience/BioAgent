"""Transport bridge for SDK local tools on OpenRouter's Chat Completions backend.

Only the wire schema uses a function call. Runner receives native shell items and
owns shell execution, approvals, hooks, tracing, and serialized resume state.
"""
from __future__ import annotations

from dataclasses import replace
import json

from agents import CustomTool, FunctionTool, OpenAIChatCompletionsModel, ShellTool
from agents.exceptions import UserError
from openai.types.responses import ResponseCustomToolCall, ResponseOutputItemAddedEvent
from openai.types.responses.response_function_shell_tool_call import ResponseFunctionShellToolCall


async def _wire_only(_context, _arguments):
    raise RuntimeError("Local tool wire schemas must never execute as FunctionTools.")


def wire_tools(tools):
    result = []
    for tool in tools:
        if isinstance(tool, CustomTool):
            result.append(FunctionTool(name=tool.name,
                description=tool.description + "\nOn this JSON transport, put the raw tool text in the input string field.",
                params_json_schema={"type": "object", "additionalProperties": False,
                    "properties": {"input": {"type": "string"}}, "required": ["input"]},
                on_invoke_tool=_wire_only))
            continue
        if not isinstance(tool, ShellTool):
            result.append(tool)
            continue
        if tool.environment.get("type") != "local":
            raise UserError("The Chat Completions shell bridge only supports local executors.")
        result.append(FunctionTool(name=tool.name,
            description="Execute one agent-pipeline command using the local runtime. Follow the pipeline command protocol in your instructions.",
            params_json_schema={"type": "object", "additionalProperties": False,
                "properties": {"commands": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
                    "timeout_ms": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "max_output_length": {"anyOf": [{"type": "integer"}, {"type": "null"}]}},
                "required": ["commands", "timeout_ms", "max_output_length"]},
            on_invoke_tool=_wire_only))
    return result


def wire_input(items, shell_name="pipeline_shell"):
    if isinstance(items, str):
        return items
    converted = []
    for raw in items:
        item = raw.model_dump() if hasattr(raw, "model_dump") else raw
        if item.get("type") == "shell_call":
            converted.append({"type": "function_call", "id": item.get("id"),
                "name": shell_name, "call_id": item["call_id"], "arguments": json.dumps(item["action"])})
        elif item.get("type") == "shell_call_output":
            converted.append({"type": "function_call_output", "call_id": item["call_id"],
                              "output": json.dumps(item["output"])})
        elif item.get("type") == "custom_tool_call":
            converted.append({"type": "function_call", "id": item.get("id"),
                "name": item["name"], "call_id": item["call_id"],
                "arguments": json.dumps({"input": item["input"]})})
        elif item.get("type") == "custom_tool_call_output":
            converted.append({"type": "function_call_output", "call_id": item["call_id"],
                              "output": item["output"]})
        else:
            converted.append(item)
    return converted


def native_item(item, shell_names, custom_names):
    if getattr(item, "type", None) == "function_call" and item.name in shell_names:
        return ResponseFunctionShellToolCall(id=item.id, call_id=item.call_id,
            action=json.loads(item.arguments), type="shell_call", status="completed")
    if getattr(item, "type", None) == "function_call" and item.name in custom_names:
        return ResponseCustomToolCall(id=item.id, call_id=item.call_id, name=item.name,
            input=json.loads(item.arguments)["input"], type="custom_tool_call")
    return item


class LocalToolsChatCompletionsModel(OpenAIChatCompletionsModel):
    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, previous_response_id=None,
                           conversation_id=None, prompt=None):
        names = {tool.name for tool in tools if isinstance(tool, ShellTool)}
        custom_names = {tool.name for tool in tools if isinstance(tool, CustomTool)}
        response = await super().get_response(system_instructions, wire_input(input), model_settings,
            wire_tools(tools), output_schema, handoffs, tracing, previous_response_id,
            conversation_id, prompt)
        return replace(response, output=[native_item(item, names, custom_names) for item in response.output])

    async def stream_response(self, system_instructions, input, model_settings, tools,
                              output_schema, handoffs, tracing, previous_response_id=None,
                              conversation_id=None, prompt=None):
        # Native actions need complete JSON. Track output indexes, because the
        # SDK can give concurrent Chat Completions items the same synthetic ID.
        names = {tool.name for tool in tools if isinstance(tool, ShellTool)}
        custom_names = {tool.name for tool in tools if isinstance(tool, CustomTool)}
        native_indexes = set()
        sequence_number = 0
        async for event in super().stream_response(system_instructions, wire_input(input), model_settings,
                wire_tools(tools), output_schema, handoffs, tracing, previous_response_id,
                conversation_id, prompt):
            if event.type == "response.output_item.added" and getattr(event.item, "name", None) in names | custom_names:
                native_indexes.add(event.output_index)
                continue
            if event.type.startswith("response.function_call_arguments.") and event.output_index in native_indexes:
                continue
            if event.type == "response.output_item.done":
                event = event.model_copy(update={"item": native_item(event.item, names, custom_names)})
                if event.output_index in native_indexes:
                    yield ResponseOutputItemAddedEvent(type="response.output_item.added",
                        item=event.item, output_index=event.output_index,
                        sequence_number=sequence_number)
                    sequence_number += 1
            elif event.type == "response.completed":
                event = event.model_copy(update={"response": event.response.model_copy(update={
                    "output": [native_item(item, names, custom_names) for item in event.response.output]})})
            yield event.model_copy(update={"sequence_number": sequence_number})
            sequence_number += 1
