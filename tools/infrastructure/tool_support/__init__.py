"""Shared SDK FunctionTool boundary helpers."""
from .decorators import bio_function_tool
from .evidence import EvidenceCollector
from .evidence_models import EvidenceArtifact, EvidenceRecord
from .guardrails import TOOL_INPUT_GUARDRAIL, TOOL_OUTPUT_GUARDRAIL
from .results import FunctionArtifact, FunctionContract, FunctionResult, ToolError, tool_error

__all__ = [
    "TOOL_INPUT_GUARDRAIL", "TOOL_OUTPUT_GUARDRAIL", "EvidenceArtifact", "EvidenceCollector", "EvidenceRecord", "load_evidence",
    "FunctionArtifact", "FunctionContract", "FunctionResult", "ToolError",
    "tool_error", "bio_function_tool",
]


def load_evidence(*args, **kwargs):
    """Load an evidence artifact without importing workspace adapters eagerly.

    ``workspace.paths`` imports ``OperationContext`` from this package.  The
    artifact module imports workspace path resolution, so importing it here
    would create a package-initialization cycle for callers that only need the
    workspace helpers.
    """
    from .artifacts import load_evidence as _load_evidence

    return _load_evidence(*args, **kwargs)
