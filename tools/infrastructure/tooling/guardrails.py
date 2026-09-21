"""SDK-native boundary checks shared by every public biological FunctionTool."""
from __future__ import annotations

import json
from typing import Any

from agents import ToolInputGuardrail, ToolInputGuardrailData, ToolOutputGuardrail, ToolOutputGuardrailData
from agents.tool_guardrails import ToolGuardrailFunctionOutput


def _input_check(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
    # Pydantic has already validated the typed schema. Keep this boundary hook
    # for common audit metadata and future path/risk checks.
    return ToolGuardrailFunctionOutput.allow({"tool": data.context.tool_name, "schema_validated": True})


def _output_check(data: ToolOutputGuardrailData) -> ToolGuardrailFunctionOutput:
    value = data.output
    try:
        parsed: Any = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return ToolGuardrailFunctionOutput.reject_content(
            "The tool returned malformed JSON; report the tool failure without inventing a result."
        )
    if not isinstance(parsed, dict) or parsed.get("status") not in {"ok", "error", "blocked"}:
        return ToolGuardrailFunctionOutput.reject_content(
            "The tool returned an invalid result envelope; report the tool failure without inventing a result."
        )
    return ToolGuardrailFunctionOutput.allow({"envelope_valid": True})


TOOL_INPUT_GUARDRAIL = ToolInputGuardrail(_input_check, name="tool_schema_boundary")
TOOL_OUTPUT_GUARDRAIL = ToolOutputGuardrail(_output_check, name="tool_result_boundary")
