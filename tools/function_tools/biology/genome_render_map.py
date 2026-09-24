"""Prepare genome features for the browser's IGV.js genome viewer."""
from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from Bio import SeqIO
from agents import RunContextWrapper
from pydantic import Field, model_validator

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, input_path, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class Feature(FunctionContract):
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    strand: Literal[-1, 0, 1]
    type: str
    label: str
    parts: list[tuple[int, int]] = Field(default_factory=list)
    qualifiers: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coordinates(self):
        if self.end < self.start or any(a < 1 or b < a for a, b in self.parts):
            raise ValueError("Features use 1-based inclusive coordinates.")
        return self


class FeatureSet(FunctionContract):
    sequence_id: str
    length: int = Field(ge=1)
    features: list[Feature]

    @model_validator(mode="after")
    def within_sequence(self):
        if any(f.end > self.length or any(b > self.length for a, b in f.parts) for f in self.features):
            raise ValueError("Feature coordinates exceed sequence length.")
        return self


class FeatureDocument(FunctionContract):
    schema_version: Literal[1] = 1
    coordinates: Literal["1-based-inclusive"] = "1-based-inclusive"
    records: list[FeatureSet]
    fasta_path: str | None = None


class MapResult(FunctionContract):
    source_path: str
    genome_map_path: str
    reference_path: str
    sequence_id: str
    genome_length: int
    total: int
    rendered: int
    truncated: bool


FEATURE_COLORS = {
    "gene": "#2563eb",
    "CDS": "#0f766e",
    "ORF": "#7c3aed",
    "tRNA": "#d97706",
    "rRNA": "#dc2626",
    "repeat_region": "#64748b",
    "misc_feature": "#475569",
}
MAX_RENDERED_FEATURES = 50_000


def _select_id(ids: list[str], selected: str | None):
    if len(ids) != len(set(ids)):
        raise ValueError("Sequence IDs must be unique.")
    if selected:
        if selected not in ids:
            raise ValueError(f"Sequence {selected!r} is not present.")
        return selected
    if len(ids) != 1:
        raise ValueError("Provide sequence_id when input contains multiple sequences.")
    return ids[0]


def _feature_rows(sequence_id: str, features: list[Feature]) -> tuple[list[dict], bool]:
    """Convert 1-based inclusive features to IGV's 0-based half-open format."""
    rows: list[dict] = []
    total_spans = sum(len(feature.parts) if feature.parts else 1 for feature in features)
    for feature in features:
        parts = feature.parts or [(feature.start, feature.end)]
        for start, end in parts:
            rows.append({
                "chr": sequence_id,
                "start": start - 1,
                "end": end,
                "name": feature.label,
                "strand": "+" if feature.strand > 0 else "-" if feature.strand < 0 else ".",
                "color": FEATURE_COLORS.get(feature.type, "#475569"),
                "feature_type": feature.type,
            })
            if len(rows) >= MAX_RENDERED_FEATURES:
                return rows, total_spans > len(rows)
    return rows, total_spans > len(rows)


def _calculate(*, features_path: str, sequence_id: str | None, label: str | None, context):
    path = input_path(context, features_path, (".json",))
    document = FeatureDocument.model_validate_json(path.read_text(encoding="utf-8"))
    selected = _select_id([record.sequence_id for record in document.records], sequence_id)
    record = next(record for record in document.records if record.sequence_id == selected)
    if not re.fullmatch(r"[A-Za-z0-9_.|+-]+", selected):
        raise ValueError("Sequence IDs for IGV must use letters, digits, underscores, dots, pipes, + or -.")
    rows, truncated = _feature_rows(selected, record.features)
    title = label or selected

    map_target = destination(context, "genome_map.json")
    reference_format = "chromsizes"
    reference_target = map_target.with_name("reference.chrom.sizes")
    reference_text = f"{selected}\t{record.length}\n"
    if document.fasta_path:
        fasta = input_path(context, document.fasta_path, (".fa", ".fasta", ".fna", ".ffn"))
        with fasta.open() as stream:
            sequences = [item for item in SeqIO.parse(stream, "fasta") if item.id == selected]
        if len(sequences) != 1 or len(sequences[0]) != record.length:
            raise ValueError("Reference FASTA must contain one matching sequence ID and length.")
        sequence = str(sequences[0].seq).upper()
        if len(sequence) > 10_000_000:
            raise ValueError("The unindexed genome viewer supports sequences up to 10 million bases.")
        if not set(sequence) <= set("ACGTURYSWKMBDHVN"):
            raise ValueError("Genome reference must contain nucleotide symbols only.")
        reference_format = "fasta"
        reference_target = map_target.with_name("reference.fasta")
        reference_text = f">{selected}\n{sequence}\n"
    reference_target.write_text(reference_text, encoding="utf-8")
    reference_file = artifact(context, reference_target)
    map_target.write_text(json.dumps({
        "schema_version": 1,
        "coordinates": "0-based-half-open",
        "title": title,
        "sequence_id": selected,
        "genome_length": record.length,
        "reference_path": reference_file["path"],
        "reference_format": reference_format,
        "total": len(record.features),
        "rendered": len(rows),
        "truncated": truncated,
        "features": rows,
    }, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    map_file = artifact(context, map_target)
    return output({
        "source_path": features_path,
        "genome_map_path": map_file["path"],
        "reference_path": reference_file["path"],
        "sequence_id": selected,
        "genome_length": record.length,
        "total": len(record.features),
        "rendered": len(rows),
        "truncated": truncated,
    }, map_file, reference_file)


@bio_function_tool(timeout=120)
async def genome_render_map(
    ctx: RunContextWrapper[AgentRunContext],
    features_path: str,
    sequence_id: str | None = None,
    label: Annotated[str | None, Field(max_length=200)] = None,
) -> FunctionResult[MapResult]:
    """Create an interactive linear IGV genome browser from genome_read_features or sequence_find_orfs output."""
    return await invoke(
        ctx.context,
        "genome_render_map",
        _calculate,
        {"features_path": features_path, "sequence_id": sequence_id, "label": label},
        FunctionResult[MapResult],
    )


__all__ = ["genome_render_map", "MapResult"]
