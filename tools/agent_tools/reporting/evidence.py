"""Evidence loading and citation checks shared by reporting agents."""
from __future__ import annotations

import json

from tools.infrastructure.tool_support.artifacts import load_evidence
from tools.infrastructure.tool_support.evidence_models import EvidenceRecord

from .contracts import ReportInput

MAX_REPORT_EVIDENCE_CHARS = 60_000


def load_report_evidence(context, paths: list[str]) -> list[EvidenceRecord]:
    records = load_evidence(context, paths)
    if not records:
        raise ValueError("Reporting requires nonempty evidence.")
    if sum(len(record.text) for record in records) > MAX_REPORT_EVIDENCE_CHARS:
        raise ValueError(
            "Use evidence_retrieve to reduce evidence to at most 60000 characters."
        )
    return records


def validate_source_ids(source_ids: list[str], records: list[EvidenceRecord]) -> None:
    known_ids = {record.id for record in records}
    if not source_ids or not set(source_ids) <= known_ids:
        raise ValueError("Report cites unknown evidence IDs or does not identify its sources.")


def evidence_prompt(context, tool_name: str, arguments: ReportInput) -> str:
    """Project the question and evidence through the public model boundary."""
    records = load_report_evidence(context.operation_context(tool_name), arguments.evidence_paths)
    return json.dumps(context.public({
        "question": arguments.question,
        "sources": [record.model_dump(mode="json") for record in records],
    }), ensure_ascii=False)


__all__ = [
    "MAX_REPORT_EVIDENCE_CHARS",
    "load_report_evidence",
    "evidence_prompt",
    "validate_source_ids",
]
