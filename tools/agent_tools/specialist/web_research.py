"""Web-research specialist agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from tools.function_tools import FUNCTION_TOOLS

from .factory import build_specialist

NAME = "web_research_specialist"
DESCRIPTION = "Coordinate a multi-source current web research question with traceable URLs."
INSTRUCTIONS = (
    "Research current questions using web_research and preserve every source URL and "
    "bounded excerpt. Use species_report or database_lookup for curated biological "
    "records when they fit better. Separate retrieved facts from interpretation and "
    "report unavailable pages rather than filling gaps from memory."
)
TOOL_NAMES = frozenset({"web_research", "species_report", "database_lookup"})


def build_web_research(model: Model | str) -> FunctionTool:
    return build_specialist(
        model, name=NAME, description=DESCRIPTION, instructions=INSTRUCTIONS,
        tool_names=TOOL_NAMES, available_tools=FUNCTION_TOOLS, max_turns=6,
    )
