"""Read GenBank or GFF annotations into a composable feature artifact."""
from __future__ import annotations

from typing import Literal
from urllib.parse import unquote

from Bio import SeqIO
from agents import RunContextWrapper
from pydantic import Field, model_validator

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import input_path, output, write_json
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


class FeaturesResult(FunctionContract):
    source_path: str
    features_path: str
    returned: int
    total: int
    truncated: bool
    records: list[FeatureSet]
    records_truncated: bool = False


def _select_id(ids: list[str], selected: str | None):
    if len(set(ids)) != len(ids):
        raise ValueError("Sequence IDs must be unique.")
    if selected:
        if selected not in ids:
            raise ValueError(f"Sequence {selected!r} is not present.")
        return selected
    if len(ids) != 1:
        raise ValueError("Provide sequence_id when input contains multiple sequences.")
    return ids[0]


def _feature_output(source_path: str, document: FeatureDocument, file: dict):
    total = sum(len(record.features) for record in document.records)
    remaining = 100
    preview = []
    for record in document.records:
        copy = record.model_dump(mode="json")
        copy["features"] = copy["features"][:remaining]
        remaining = max(0, remaining - len(copy["features"]))
        preview.append(copy)
    returned = 100 - remaining
    return output({"source_path": source_path, "features_path": file["path"], "records": preview, "total": total, "returned": returned, "truncated": total > returned}, file)


def _gff_qualifiers(raw: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for pair in raw.split(";"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        values[key] = [unquote(item) for item in value.split(",")]
    return values


def _calculate(*, path: str, fasta_path: str | None, sequence_id: str | None, context):
    source = input_path(context, path, (".gb", ".gbk", ".genbank", ".gff", ".gff3"))
    if source.suffix.lower() in {".gff", ".gff3"}:
        if not fasta_path:
            raise ValueError("GFF input requires fasta_path for sequence IDs and lengths.")
        fasta = input_path(context, fasta_path, (".fa", ".fasta", ".fna"))
        with fasta.open() as stream:
            sequences = {}
            for record in SeqIO.parse(stream, "fasta"):
                if record.id in sequences:
                    raise ValueError("Duplicate FASTA sequence IDs.")
                sequences[record.id] = len(record)
        selected = _select_id(list(sequences), sequence_id)
        features = []
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            if line == "##FASTA":
                break
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 9:
                raise ValueError("GFF rows must contain nine tab-separated fields.")
            if parts[0] != selected:
                continue
            qualifiers = _gff_qualifiers(parts[8])
            label = (qualifiers.get("Name") or qualifiers.get("ID") or [parts[2]])[0]
            features.append(Feature(start=int(parts[3]), end=int(parts[4]), strand={"+": 1, "-": -1}.get(parts[6], 0), type=parts[2], label=label, qualifiers=qualifiers))
        dataset = FeatureSet(sequence_id=selected, length=sequences[selected], features=features)
    else:
        if fasta_path:
            raise ValueError("GenBank includes the sequence; omit fasta_path.")
        with source.open() as stream:
            all_records = list(SeqIO.parse(stream, "genbank"))
        selected = _select_id([record.id for record in all_records], sequence_id)
        record = next(record for record in all_records if record.id == selected)
        features = []
        for item in record.features:
            if item.type == "source" or item.location is None:
                continue
            parts = [(int(part.start) + 1, int(part.end)) for part in item.location.parts]
            qualifiers = {key: [str(value) for value in values] for key, values in item.qualifiers.items()}
            label = next(iter(qualifiers.get("gene") or qualifiers.get("locus_tag") or [item.type]))
            features.append(Feature(start=min(a for a, _ in parts), end=max(b for _, b in parts), strand=item.location.strand or 0, type=item.type, label=label, parts=parts if len(parts) > 1 else [], qualifiers=qualifiers))
        dataset = FeatureSet(sequence_id=selected, length=len(record), features=features)
    if len(dataset.features) > 50000:
        raise ValueError("More than 50000 features; select a smaller annotation file.")
    document = FeatureDocument(records=[dataset])
    file = write_json(context, "features.json", document.model_dump(mode="json"))
    return _feature_output(path, document, file)


@bio_function_tool(timeout=120)
async def genome_read_features(ctx: RunContextWrapper[AgentRunContext], path: str, fasta_path: str | None = None, sequence_id: str | None = None) -> FunctionResult[FeaturesResult]:
    """Read GenBank or GFF annotations into a feature artifact."""
    return await invoke(ctx.context, "genome_read_features", _calculate, {"path": path, "fasta_path": fasta_path, "sequence_id": sequence_id}, FunctionResult[FeaturesResult])


__all__ = ["genome_read_features", "FeatureDocument", "FeaturesResult"]
