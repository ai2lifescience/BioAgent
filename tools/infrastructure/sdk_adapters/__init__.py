"""OpenAI Agents SDK adapters backed by the infrastructure services."""

from .pipeline_shell import PIPELINE_INSTRUCTIONS, pipeline_shell

RUNTIME_TOOLS = [pipeline_shell]

__all__ = ["PIPELINE_INSTRUCTIONS", "RUNTIME_TOOLS", "pipeline_shell"]
