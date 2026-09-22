"""Registry for domain specialists exposed to the root agent.

This registry intentionally owns only ``Agent.as_tool()`` specialists.  The
root application registry in :mod:`tools.registry` adds these to the public
function, hosted, and runtime tool categories.
"""

from __future__ import annotations

from agents import FunctionTool, Model

from .specialist.coding import DESCRIPTION as CODING_DESCRIPTION
from .specialist.coding import INSTRUCTIONS as CODING_INSTRUCTIONS
from .specialist.coding import NAME as CODING_NAME
from .specialist.coding import TOOL_NAMES as CODING_TOOL_NAMES
from .specialist.coding import build_coding
from .specialist.data_analysis import DESCRIPTION as DATA_DESCRIPTION
from .specialist.data_analysis import INSTRUCTIONS as DATA_INSTRUCTIONS
from .specialist.data_analysis import NAME as DATA_NAME
from .specialist.data_analysis import TOOL_NAMES as DATA_TOOL_NAMES
from .specialist.data_analysis import build_data_analysis
from .specialist.document import DESCRIPTION as DOCUMENT_DESCRIPTION
from .specialist.document import INSTRUCTIONS as DOCUMENT_INSTRUCTIONS
from .specialist.document import NAME as DOCUMENT_NAME
from .specialist.document import TOOL_NAMES as DOCUMENT_TOOL_NAMES
from .specialist.document import build_document
from .specialist.pipeline import DESCRIPTION as PIPELINE_DESCRIPTION
from .specialist.pipeline import INSTRUCTIONS as PIPELINE_INSTRUCTIONS
from .specialist.pipeline import NAME as PIPELINE_NAME
from .specialist.pipeline import TOOL_NAMES as PIPELINE_TOOL_NAMES
from .specialist.pipeline import build_pipeline
from .specialist.research import NAME as RESEARCH_NAME, DESCRIPTION as RESEARCH_DESCRIPTION, INSTRUCTIONS as RESEARCH_INSTRUCTIONS, TOOL_NAMES as RESEARCH_TOOL_NAMES, build_research


SPECIALIST_GROUPS: tuple[tuple[str, str, str, set[str]], ...] = (
    (RESEARCH_NAME, RESEARCH_DESCRIPTION, RESEARCH_INSTRUCTIONS, set(RESEARCH_TOOL_NAMES) | {"report_review", "report_synthesize"}),
    (PIPELINE_NAME, PIPELINE_DESCRIPTION, PIPELINE_INSTRUCTIONS, set(PIPELINE_TOOL_NAMES)),
    (DOCUMENT_NAME, DOCUMENT_DESCRIPTION, DOCUMENT_INSTRUCTIONS, set(DOCUMENT_TOOL_NAMES)),
    (DATA_NAME, DATA_DESCRIPTION, DATA_INSTRUCTIONS, set(DATA_TOOL_NAMES)),
    (CODING_NAME, CODING_DESCRIPTION, CODING_INSTRUCTIONS, set(CODING_TOOL_NAMES)),
)

SPECIALIST_BUILDERS = (
    build_research,
    build_pipeline,
    build_document,
    build_data_analysis,
    build_coding,
)


def build_specialist_tools(model: Model | str) -> list[FunctionTool]:
    """Build every registered specialist as an SDK agent-as-tool."""
    return [builder(model) for builder in SPECIALIST_BUILDERS]
