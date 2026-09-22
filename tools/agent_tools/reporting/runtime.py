"""Shared nested-agent extraction and result recording for report tools."""
from __future__ import annotations

from typing import Any

from agents import RunResult, RunResultStreaming

from tools.infrastructure.tool_support.results import FunctionResult

from .contracts import ReportDraft, ReportInput, ReviewResult
from .evidence import load_report_evidence, validate_source_ids


async def extract_report_result(
    result: RunResult | RunResultStreaming,
    *,
    tool_name: str,
    input_model: type[ReportInput],
    output_model: type[ReviewResult] | type[ReportDraft],
) -> str:
    """Validate a nested report output and return the standard tool envelope."""
    output = output_model.model_validate(result.final_output)
    wrapper = result.context_wrapper
    arguments = input_model.model_validate(wrapper.tool_input)
    records = load_report_evidence(
        wrapper.context.operation_context(tool_name), arguments.evidence_paths
    )
    validate_source_ids(output.source_ids, records)

    public = wrapper.context.public(output.model_dump(mode="json"))
    envelope = FunctionResult[dict[str, Any]](status="ok", data=public)
    wrapper.context.tool_results.append(
        wrapper.context.public(
            {
                "tool": tool_name,
                "arguments": arguments.model_dump(mode="json"),
                "result": public,
                "status": "ok",
                "error": None,
                "error_type": None,
                "tool_calls": [],
            }
        )
    )
    return envelope.model_dump_json()


__all__ = ["extract_report_result"]
