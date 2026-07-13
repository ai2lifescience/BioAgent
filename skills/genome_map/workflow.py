"""Genome map skill workflow."""

from __future__ import annotations

from typing import Any

from execution.skill_context import SkillContext, ensure_skill_context


SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "genome_map",
        "description": (
            "Create a genome feature map from GenBank, GFF+FASTA, or FASTA. "
            "Use for genome structure, genome map, gene layout, feature layout, "
            "circular genome maps, linear genome maps, and ORF maps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fasta_path": {"type": "string", "description": "Local FASTA file path."},
                "genbank_path": {"type": "string", "description": "Local GenBank .gb/.gbk file path."},
                "gff_path": {"type": "string", "description": "Optional local GFF/GFF3 annotation path."},
                "artifact_ref": {
                    "type": "string",
                    "enum": ["latest_fasta"],
                    "description": "Use latest_fasta to map the newest FASTA artifact in this session.",
                },
                "layout": {"type": "string", "enum": ["circular", "linear"], "default": "circular"},
                "label": {"type": "string", "description": "Optional map label."},
                "min_orf_length": {"type": "integer", "default": 90},
            },
            "anyOf": [
                {"required": ["fasta_path"]},
                {"required": ["genbank_path"]},
                {"required": ["artifact_ref"]},
            ],
            "additionalProperties": False,
        },
    },
}


def genome_map(
    fasta_path: str | None = None,
    genbank_path: str | None = None,
    gff_path: str | None = None,
    artifact_ref: str | None = None,
    layout: str = "circular",
    label: str | None = None,
    min_orf_length: int = 90,
    context: SkillContext | None = None,
) -> dict[str, Any]:
    context = ensure_skill_context(context, "genome_map")
    source_artifact = None
    if _should_use_latest_fasta(fasta_path=fasta_path, genbank_path=genbank_path, artifact_ref=artifact_ref):
        source_artifact = context.latest_artifact(
            kinds=("fasta",),
            suffixes=(".fasta", ".fa", ".fna", ".faa"),
        )
        if not source_artifact:
            raise ValueError(
                "No FASTA artifact is available in this session. "
                "Download or provide a FASTA/GenBank file path first."
            )
        fasta_path = str(source_artifact["path"])

    result = context.run_tool(
        "genome_map",
        {
            "fasta_path": fasta_path,
            "genbank_path": genbank_path,
            "gff_path": gff_path,
            "output_dir": context.artifact_path("genome_maps"),
            "label": label,
            "layout": layout,
            "min_orf_length": min_orf_length,
        },
    )["result"]
    lines = [
        "Genome map created.",
        f"Label: {result.get('label')}",
        f"Layout: {result.get('layout')}",
        f"Genome length: {result.get('genome_length')} bp",
        f"Features: {result.get('feature_count', 0)}",
        f"Genes: {result.get('gene_count', 0)}",
        f"CDS: {result.get('cds_count', 0)}",
        f"ORFs: {result.get('orf_count', 0)}",
        f"Image: {result.get('image_path')}",
    ]
    return {
        "skill": "genome_map",
        "tool": "genome_map",
        "answer": "\n".join(lines),
        "source_artifact": source_artifact,
        **result,
    }


def _should_use_latest_fasta(
    fasta_path: str | None,
    genbank_path: str | None,
    artifact_ref: str | None,
) -> bool:
    if fasta_path or genbank_path:
        return False
    if artifact_ref == "latest_fasta":
        return True
    return True
