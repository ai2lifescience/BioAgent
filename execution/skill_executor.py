"""Skill execution and model skill-call parsing."""

from __future__ import annotations

import json
from inspect import signature
from typing import Any, Callable

from execution.skill_context import SkillContext
from execution.tool_executor import ToolExecutor
from registries.skill_registry import SKILLS, get_skill_definition


def message_to_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, dict):
        return dict(message)

    data = {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", None),
    }
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = tool_calls
    return data


def llm_skill_calls_from_message(message: Any) -> list[Any]:
    if isinstance(message, dict):
        return message.get("tool_calls") or []
    return getattr(message, "tool_calls", None) or []


def skill_call_parts(skill_call: Any) -> tuple[str, str, dict[str, Any]]:
    if isinstance(skill_call, dict):
        call_id = skill_call.get("id", "")
        function = skill_call.get("function", {})
        name = function.get("name", "")
        raw_args = function.get("arguments") or "{}"
    else:
        call_id = getattr(skill_call, "id", "")
        function = getattr(skill_call, "function", None)
        name = getattr(function, "name", "")
        raw_args = getattr(function, "arguments", "{}")

    if isinstance(raw_args, dict):
        return call_id, name, raw_args

    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        args = {"_raw_arguments": raw_args, "_argument_error": "Invalid JSON arguments."}
    return call_id, name, args


class SkillExecutor:
    """Execute registered skill workflows behind the agent boundary."""

    def __init__(
        self,
        skills: dict[str, Callable[..., dict[str, Any]]] | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.skills = skills or SKILLS
        self.tool_executor = tool_executor or ToolExecutor()

    def execute_skill(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        log_fn: Callable[[str], None] | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        if args.get("_argument_error"):
            return {
                "skill": name,
                "arguments": args,
                "result": {"error": args["_argument_error"], "raw_arguments": args.get("_raw_arguments")},
                "tool_calls": [],
            }

        if name not in self.skills:
            return {
                "skill": name,
                "category": "unknown",
                "execution_branch": "unknown",
                "arguments": args,
                "result": {"error": f"Unknown skill: {name}"},
                "tool_calls": [],
            }

        definition = get_skill_definition(name)
        category = definition.category if definition else "general"
        allowed_tools = definition.tools if definition else ()
        if log_fn:
            log_fn(f"[skill_executor] Running skill {name} via {category}.")

        handler = self.skills[name]
        context = SkillContext(
            skill_name=name,
            allowed_tools=allowed_tools,
            tool_executor=self.tool_executor,
            user_context=user_context,
            log_fn=log_fn,
        )
        skill_args = dict(args)
        if self._accepts_parameter(handler, "context"):
            skill_args["context"] = context
        if log_fn and self._accepts_parameter(handler, "log_fn"):
            skill_args["log_fn"] = log_fn

        try:
            result = handler(**skill_args)
        except Exception as exc:
            result = {"error": str(exc), "error_type": type(exc).__name__}

        return {
            "skill": name,
            "category": category,
            "execution_branch": self._branch_for_category(category),
            "arguments": args,
            "result": result,
            "tool_calls": context.tool_calls,
        }

    def execute_llm_skill_call(
        self,
        skill_call: Any,
        log_fn: Callable[[str], None] | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        call_id, name, args = skill_call_parts(skill_call)
        return call_id, self.execute_skill(
            name=name,
            arguments=args,
            log_fn=log_fn,
            user_context=user_context,
        )

    @staticmethod
    def _branch_for_category(category: str) -> str:
        return {
            "bio_api": "Bio APIs",
            "bio_data": "Bio APIs",
            "bio_tool": "Bio Tools",
            "retrieval": "Retrieval",
            "file_io": "File I/O",
            "diagnostics": "Tools",
        }.get(category, "Tools")

    @staticmethod
    def _accepts_parameter(handler: Callable[..., dict[str, Any]], name: str) -> bool:
        return name in signature(handler).parameters
