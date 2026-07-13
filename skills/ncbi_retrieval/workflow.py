"""NCBI retrieval skill workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context
from bio_data.ncbi import format_ncbi_result
from bio_data.ncbi_entrez.spec import DEFAULT_OUTPUT_DIR_PREFIX, DEFAULT_OUTPUT_DIR_TEMPLATE


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "ncbi_retrieval",
        "description": (
            "Workflow for searching NCBI Entrez and downloading public sequence "
            "records as FASTA plus metadata CSV files. Use for NCBI, Entrez, "
            "FASTA, nucleotide, protein, genome, gene, accession, or PubMed data "
            "retrieval requests."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "terms": {"type": "array", "items": {"type": "string"}},
                "genes": {"type": "array", "items": {"type": "string"}},
                "accessions": {"type": "array", "items": {"type": "string"}},
                "db": {"type": "string", "default": "nucleotide"},
                "max_records": {"type": "integer", "default": 10, "minimum": 1},
                "year": {"type": "integer", "minimum": 1},
                "year_start": {"type": "integer", "minimum": 1},
                "year_end": {"type": "integer", "minimum": 1},
                "date_field": {"type": "string", "default": "PDAT", "enum": ["PDAT", "MDAT"]},
                "output_dir": {"type": "string"},
                "filename": {"type": "string"},
                "metadata_filename": {"type": "string"},
            },
            "anyOf": [
                {"required": ["term"]},
                {"required": ["terms"]},
                {"required": ["accessions"]},
            ],
            "additionalProperties": False,
        },
    },
}


def ncbi_retrieval(
    context: SkillContext | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "ncbi_retrieval")
    output_dir = kwargs.get("output_dir")
    if _is_default_output_dir(output_dir):
        output_name = Path(str(output_dir or DEFAULT_OUTPUT_DIR_PREFIX)).name
        kwargs["output_dir"] = context.artifact_path("downloads", output_name)
    result = context.run_tool("ncbi_fetch", kwargs)["result"]
    answer = format_ncbi_result(result=result, fetch_args=kwargs)
    return {
        "skill": "ncbi_retrieval",
        "tool": "ncbi_fetch",
        "answer": answer,
        **result,
    }


def _is_default_output_dir(output_dir: Any) -> bool:
    if not output_dir:
        return True
    value = str(output_dir)
    return value in {DEFAULT_OUTPUT_DIR_PREFIX, DEFAULT_OUTPUT_DIR_TEMPLATE} or value.startswith(
        f"{DEFAULT_OUTPUT_DIR_PREFIX}_"
    )
