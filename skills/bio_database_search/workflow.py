"""Biological database lookup skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "database_lookup",
        "description": (
            "Workflow for querying UniProt, InterPro, KEGG, QuickGO, PDB, and "
            "AlphaFold DB for proteins, functions, pathways, ontology annotations, "
            "and structures."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["uniprot", "interpro", "kegg", "quickgo", "pdb", "alphafold"],
                },
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
                "operation": {"type": "string"},
                "taxid": {"type": "integer", "minimum": 1},
                "download": {"type": "boolean", "default": False},
                "file_format": {"type": "string", "enum": ["cif", "pdb"], "default": "cif"},
                "output_dir": {"type": "string"},
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
    operation: str | None = None,
    taxid: int | None = None,
    download: bool = False,
    file_format: str = "cif",
    output_dir: str | None = None,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "database_lookup")
    payload: dict[str, Any] = {
        "database": database,
        "query": query,
        "max_results": max_results,
        "download": download,
        "file_format": file_format,
    }
    if operation:
        payload["operation"] = operation
    if taxid is not None:
        payload["taxid"] = taxid
    if output_dir:
        payload["output_dir"] = output_dir
    result = context.run_tool(
        "bio_database_search",
        payload,
    )["result"]
    lines = [
        f"{result.get('database', 'database')} search completed.",
        f"Query: {result.get('query', query)}",
        f"Records returned: {result.get('record_count', 0)}",
    ]
    for item in result.get("records", [])[:10]:
        record_id = (
            item.get("accession")
            or item.get("entry_id")
            or item.get("entry")
            or item.get("identifier")
            or item.get("id")
        )
        label = (
            item.get("name")
            or item.get("protein_name")
            or item.get("title")
            or item.get("definition")
            or item.get("value")
            or item.get("organism")
            or ""
        )
        url = item.get("url") or ""
        lines.append(f"- {record_id}: {label} {url}".strip())
    return {
        "skill": "database_lookup",
        "tool": "bio_database_search",
        "answer": "\n".join(lines),
        **result,
    }
