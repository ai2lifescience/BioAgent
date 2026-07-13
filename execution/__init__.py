"""Skill and tool execution boundary for BioAgent."""

__all__ = [
    "SkillContext",
    "SkillExecutor",
    "ToolExecutor",
    "ensure_skill_context",
    "llm_skill_calls_from_message",
    "message_to_dict",
]


def __getattr__(name: str):
    if name in {"SkillContext", "ensure_skill_context"}:
        from execution.skill_context import SkillContext, ensure_skill_context

        return {
            "SkillContext": SkillContext,
            "ensure_skill_context": ensure_skill_context,
        }[name]
    if name in {"SkillExecutor", "llm_skill_calls_from_message", "message_to_dict"}:
        from execution.skill_executor import (
            SkillExecutor,
            llm_skill_calls_from_message,
            message_to_dict,
        )

        return {
            "SkillExecutor": SkillExecutor,
            "llm_skill_calls_from_message": llm_skill_calls_from_message,
            "message_to_dict": message_to_dict,
        }[name]
    if name == "ToolExecutor":
        from execution.tool_executor import ToolExecutor

        return ToolExecutor
    raise AttributeError(name)
