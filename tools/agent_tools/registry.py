"""Registry for domain specialists exposed to the root agent."""

from __future__ import annotations

from agents import FunctionTool, Model

from .pipeline_specialist import DESCRIPTION as PIPELINE_DESCRIPTION
from .pipeline_specialist import INSTRUCTIONS as PIPELINE_INSTRUCTIONS
from .pipeline_specialist import NAME as PIPELINE_NAME
from .pipeline_specialist import TOOL_NAMES as PIPELINE_TOOL_NAMES
from .pipeline_specialist import build_pipeline_specialist
from .retrieval_specialist import DESCRIPTION as RETRIEVAL_DESCRIPTION
from .retrieval_specialist import INSTRUCTIONS as RETRIEVAL_INSTRUCTIONS
from .retrieval_specialist import NAME as RETRIEVAL_NAME
from .retrieval_specialist import TOOL_NAMES as RETRIEVAL_TOOL_NAMES
from .retrieval_specialist import build_retrieval_specialist
from .sequence_specialist import DESCRIPTION as SEQUENCE_DESCRIPTION
from .sequence_specialist import INSTRUCTIONS as SEQUENCE_INSTRUCTIONS
from .sequence_specialist import NAME as SEQUENCE_NAME
from .sequence_specialist import TOOL_NAMES as SEQUENCE_TOOL_NAMES
from .sequence_specialist import build_sequence_specialist


SPECIALIST_GROUPS: tuple[tuple[str, str, str, set[str]], ...] = (
    (SEQUENCE_NAME, SEQUENCE_DESCRIPTION, SEQUENCE_INSTRUCTIONS, set(SEQUENCE_TOOL_NAMES)),
    (RETRIEVAL_NAME, RETRIEVAL_DESCRIPTION, RETRIEVAL_INSTRUCTIONS, set(RETRIEVAL_TOOL_NAMES)),
    (PIPELINE_NAME, PIPELINE_DESCRIPTION, PIPELINE_INSTRUCTIONS, set(PIPELINE_TOOL_NAMES)),
)

SPECIALIST_BUILDERS = (
    build_sequence_specialist,
    build_retrieval_specialist,
    build_pipeline_specialist,
)


def build_specialist_tools(model: Model | str) -> list[FunctionTool]:
    """Build every registered specialist as an SDK agent-as-tool."""
    return [builder(model) for builder in SPECIALIST_BUILDERS]
