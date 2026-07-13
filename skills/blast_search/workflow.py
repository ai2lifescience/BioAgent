"""BLAST search skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "blast_search",
        "description": (
            "Workflow for submitting a sequence to NCBI BLAST or polling an "
            "existing BLAST RID. Use only when the user explicitly asks for "
            "BLAST or sequence similarity search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sequence": {"type": "string"},
                "rid": {"type": "string", "description": "Existing BLAST request ID to poll."},
                "program": {
                    "type": "string",
                    "enum": ["blastn", "blastp", "blastx", "tblastn", "tblastx"],
                    "default": "blastn",
                },
                "database": {"type": "string", "default": "nt"},
                "hitlist_size": {"type": "integer", "default": 10},
                "expect": {"type": "number", "default": 10.0},
                "wait": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 120},
            },
            "anyOf": [
                {"required": ["sequence"]},
                {"required": ["rid"]},
            ],
            "additionalProperties": False,
        },
    },
}


def blast_search(
    sequence: str | None = None,
    rid: str | None = None,
    program: str = "blastn",
    database: str = "nt",
    hitlist_size: int = 10,
    expect: float = 10.0,
    wait: bool = False,
    timeout_seconds: int = 120,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "blast_search")
    result = context.run_tool(
        "blast_search",
        {
            "sequence": sequence,
            "rid": rid,
            "program": program,
            "database": database,
            "hitlist_size": hitlist_size,
            "expect": expect,
            "wait": wait,
            "timeout_seconds": timeout_seconds,
        }
    )["result"]
    answer = _format_blast_answer(result)
    return {"skill": "blast_search", "tool": "blast_search", "answer": answer, **result}


def _format_blast_answer(result: dict[str, Any]) -> str:
    lines = [
        "BLAST request completed.",
        f"Program: {result.get('program')}",
        f"Database: {result.get('database')}",
        f"RID: {result.get('rid')}",
        f"Status: {result.get('status')}",
    ]

    if result.get("status") == "SUBMITTED":
        estimated = result.get("estimated_seconds")
        if estimated:
            lines.append(f"Estimated wait: {estimated} seconds")
        lines.append("No hits are available yet. Ask to poll this RID or run BLAST with wait=true.")
        return "\n".join(lines)

    if result.get("parse_error"):
        lines.append(f"Parse warning: {result['parse_error']}")

    hits = result.get("hits")
    if not isinstance(hits, list):
        return "\n".join(lines)

    lines.append(f"Hits: {len(hits)}")
    for hit in hits[:5]:
        title = hit.get("title") or hit.get("accession") or hit.get("id") or "unknown hit"
        details = []
        if hit.get("accession"):
            details.append(f"accession {hit['accession']}")
        if hit.get("percent_identity") is not None:
            details.append(f"{hit['percent_identity']}% identity")
        if hit.get("evalue") is not None:
            details.append(f"e={hit['evalue']}")
        if hit.get("bit_score") is not None:
            details.append(f"bit score {hit['bit_score']}")
        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- {title}{suffix}")
    return "\n".join(lines)
