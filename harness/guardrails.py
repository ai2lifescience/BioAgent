"""Input and output guardrails for biological requests."""

from __future__ import annotations

import re
from typing import Any

from agents import Agent, InputGuardrail, OutputGuardrail, RunContextWrapper
from agents.guardrail import GuardrailFunctionOutput

from .context import BioRunContext


SENSITIVE = re.compile(
    r"\b(gain[- ]of[- ]function|increase infectivity|increase virulence|"
    r"evade immunity|immune escape|synthesize virus|make pathogen|weaponize|"
    r"enhance pathogenicity|engineer transmissibility|serial passage|"
    r"design (?:a |the )?(?:pathogen|virus|toxin))\b",
    re.IGNORECASE,
)
BIOLOGICAL = re.compile(
    r"\b(species|organism|genome|gene|protein|sequence|ncbi|pubmed|fasta|virus|phage|strain)\b",
    re.IGNORECASE,
)


def _input_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


async def input_check(
    context: RunContextWrapper[BioRunContext],
    _agent: Agent[BioRunContext],
    input_data: Any,
) -> GuardrailFunctionOutput:
    text = _input_text(input_data)
    blocked = bool(SENSITIVE.search(text))
    if blocked:
        context.context.record("guardrail_blocked", guardrail="input", reason="sensitive_request")
    return GuardrailFunctionOutput(
        output_info={"sensitive_request": blocked},
        tripwire_triggered=blocked,
    )


async def output_check(
    context: RunContextWrapper[BioRunContext],
    _agent: Agent[BioRunContext],
    output: Any,
) -> GuardrailFunctionOutput:
    text = str(output or "")
    warnings: list[str] = []
    if BIOLOGICAL.search(text) and not context.context.tool_results:
        warnings.append("Biological claims were returned without a registered evidence tool.")
    if not text.strip():
        warnings.append("The agent returned an empty answer.")
    context.context.record("guardrail_completed", guardrail="output", warnings=warnings)
    return GuardrailFunctionOutput(output_info={"warnings": warnings}, tripwire_triggered=not text.strip())


INPUT_GUARDRAIL = InputGuardrail(guardrail_function=input_check, name="bio_safety_input", run_in_parallel=False)
OUTPUT_GUARDRAIL = OutputGuardrail(guardrail_function=output_check, name="bio_evidence_output")
