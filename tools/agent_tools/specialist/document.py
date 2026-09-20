"""Document-workspace specialist agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from tools.function_tools import FUNCTION_TOOLS

from .factory import build_specialist

NAME = "document_specialist"
DESCRIPTION = "Find, read, and synthesize uploaded documents while preserving file and page evidence."
INSTRUCTIONS = (
    "Handle document questions with the smallest necessary set of workspace tools. "
    "Use workspace_search to locate passages across files, document_read for selectable "
    "PDF pages, and file_inspection for metadata. Preserve workspace paths, page markers, "
    "and OCR limitations; never infer text that a tool did not extract."
)
TOOL_NAMES = frozenset({"workspace_search", "document_read", "file_inspection"})


def build_document(model: Model | str) -> FunctionTool:
    return build_specialist(
        model, name=NAME, description=DESCRIPTION, instructions=INSTRUCTIONS,
        tool_names=TOOL_NAMES, available_tools=FUNCTION_TOOLS, max_turns=6,
    )
