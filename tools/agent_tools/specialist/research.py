"""Research specialist composes evidence collection, synthesis, and writing."""
from agents import FunctionTool, Model
from tools.function_tools import FUNCTION_TOOLS
from tools.agent_tools.reporting import build_report_review, build_report_synthesize
from .factory import build_specialist

NAME = "research_specialist"
DESCRIPTION = "Coordinate multi-source evidence collection, review, synthesis, and optional report writing."
INSTRUCTIONS = (
    "Choose pubmed_search or web_search according to the question. Pass returned evidence_path values "
    "to evidence_index/evidence_retrieve when ranking or persistent retrieval is helpful. Use web_fetch "
    "when a search snippet is insufficient, database_lookup for curated biological metadata, "
    "and evidence_index/evidence_retrieve when ranking or persistent retrieval is helpful. Use report_review "
    "when an independent evidence assessment is useful, then use report_synthesize for a cited draft. "
    "Web search provides snippets, not full pages. Preserve evidence limitations. Use report_write only "
    "when a saved report is requested. All paths must be workspace-relative. Do not invent evidence or "
    "copy a source into a new artifact to pretend it was retrieved."
)
TOOL_NAMES = frozenset({"pubmed_search", "web_search", "web_fetch", "database_lookup", "evidence_index", "evidence_retrieve", "report_write"})


def build_research(model: Model | str) -> FunctionTool:
    return build_specialist(model, name=NAME, description=DESCRIPTION, instructions=INSTRUCTIONS,
                            tool_names=TOOL_NAMES, available_tools=FUNCTION_TOOLS,
                            extra_tools=[build_report_review(model), build_report_synthesize(model)], max_turns=10)
