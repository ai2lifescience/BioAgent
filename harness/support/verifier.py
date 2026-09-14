"""Verification checks for BioAgent runs."""

from __future__ import annotations

import re
from typing import Any


BIO_TERMS = re.compile(
    r"\b(species|organism|genome|gene|protein|sequence|ncbi|pubmed|fasta|virus|phage|strain)\b",
    flags=re.IGNORECASE,
)


class Verifier:
    """Apply lightweight checks before returning an answer."""

    def verify(
        self,
        user_request: str,
        skill_results: list[dict[str, Any]],
        evidence: dict[str, Any] | None = None,
        allow_model_knowledge: bool = False,
    ) -> dict[str, Any]:
        warnings: list[str] = []
        errors: list[str] = []
        evidence = evidence or {}

        for record in skill_results:
            result = record.get("result")
            if isinstance(result, dict) and result.get("error"):
                errors.append(f"{record.get('skill', 'skill')} failed: {result['error']}")

        if BIO_TERMS.search(user_request) and not skill_results and not allow_model_knowledge:
            warnings.append(
                "No retrieval or database skill was used; treat unsupported biological "
                "claims as unverified."
            )

        if re.search(
            r"\b(gain of function|increase infectivity|evade immunity|synthesize virus|make pathogen)\b",
            user_request,
            re.IGNORECASE,
        ):
            warnings.append(
                "Potential biosafety-sensitive request detected; avoid procedural "
                "guidance that could enable harmful biological work."
            )

        diagnostic_only = bool(skill_results) and all(
            record.get("skill") == "example_skill" for record in skill_results
        )
        waiting_for_input = any(
            isinstance(record.get("result"), dict) and record["result"].get("needs_input")
            for record in skill_results
        )
        if (
            skill_results
            and not diagnostic_only
            and not waiting_for_input
            and not evidence.get("files")
            and not evidence.get("citations")
            and not evidence.get("record_ids")
        ):
            warnings.append(
                "No file outputs, source citations, or record IDs were collected from the executed skills."
            )

        status = "ok"
        if warnings:
            status = "warning"
        if errors:
            status = "error"

        return {
            "status": status,
            "warnings": warnings,
            "errors": errors,
        }
