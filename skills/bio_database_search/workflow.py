"""Biological database lookup skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "database_lookup",
        "description": (
            "Workflow for searching biological databases such as UniProt and PDB "
            "for proteins, genes, structures, accessions, and biomolecular records."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "database": {"type": "string", "enum": ["uniprot", "pdb"]},
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
            },
            "required": ["database", "query"],
            "additionalProperties": False,
        },
    },
}


def database_lookup(
    database: str,
    query: str,
    max_results: int = 5,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "database_lookup")
    result = context.run_tool(
        "bio_database_search",
        {"database": database, "query": query, "max_results": max_results}
    )["result"]
    lines = [
        f"{result.get('database', 'database')} search completed.",
        f"Query: {result.get('query', query)}",
        f"Records returned: {result.get('record_count', 0)}",
    ]
    for item in result.get("records", [])[:10]:
        record_id = item.get("accession") or item.get("identifier") or item.get("id")
        label = item.get("name") or item.get("title") or item.get("organism") or ""
        url = item.get("url") or ""
        lines.append(f"- {record_id}: {label} {url}".strip())
    return {
        "skill": "database_lookup",
        "tool": "bio_database_search",
        "answer": "\n".join(lines),
        **result,
    }
