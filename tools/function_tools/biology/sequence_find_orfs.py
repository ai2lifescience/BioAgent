"""Find bounded open reading frames in nucleotide records."""
from __future__ import annotations

from io import StringIO
from itertools import islice
from typing import Annotated, Literal

from Bio import SeqIO
from Bio.Seq import Seq
from agents import RunContextWrapper
from pydantic import Field, model_validator

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, input_path, output, write_json
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class SequenceSource(FunctionContract):
    sequence: str | None = Field(default=None, max_length=1_000_000)
    path: str | None = Field(default=None, description="Workspace-relative FASTA path.")
    sequence_type: Literal["auto", "dna", "rna", "protein"] = "auto"

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.sequence) == bool(self.path):
            raise ValueError("Provide exactly one of sequence or path.")
        return self


class Feature(FunctionContract):
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    strand: Literal[-1, 0, 1]
    type: str
    label: str
    parts: list[tuple[int, int]] = Field(default_factory=list)

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


class FeaturesResult(FunctionContract):
    source_path: str
    features_path: str
    returned: int
    total: int
    truncated: bool
    records: list[FeatureSet]
    records_truncated: bool = False


DNA = set("ACGTRYSWKMBDHVN")
RNA = set("ACGURYSWKMBDHVN")
AMINO = set("ACDEFGHIKLMNPQRSTVWYBXZJUO*")


def _records(source: dict, max_records: int, context):
    src = SequenceSource.model_validate(source)
    stream = input_path(context, src.path, (".fa", ".fasta", ".fna", ".faa", ".ffn")).open() if src.path else StringIO(src.sequence)
    with stream:
        if not src.path and not src.sequence.lstrip().startswith(">"):
            from Bio.SeqRecord import SeqRecord
            items = [SeqRecord(Seq("".join(src.sequence.split()).upper()), id="sequence_1")]
        else:
            items = list(islice(SeqIO.parse(stream, "fasta"), max_records + 1))
    if not items:
        raise ValueError("No sequence records found.")
    chosen = items[:max_records]
    if any(not len(item) for item in chosen):
        raise ValueError("Empty sequences are not supported.")
    if sum(len(item) for item in chosen) > 2_000_000:
        raise ValueError("Selected records exceed 2 million symbols; select a smaller file or record limit.")
    if len({item.id for item in chosen}) != len(chosen):
        raise ValueError("FASTA record IDs must be unique.")
    return src, chosen, len(items) > max_records


def _sequence_type(value: str, requested: str) -> str:
    letters = set(value.upper())
    if requested != "auto":
        allowed = {"dna": DNA, "rna": RNA, "protein": AMINO}[requested]
        if not letters <= allowed:
            raise ValueError(f"Invalid {requested} symbols: {''.join(sorted(letters - allowed))}")
        return requested
    if letters <= DNA:
        return "dna"
    if letters <= RNA:
        return "rna"
    if letters <= AMINO:
        return "protein"
    raise ValueError("Unrecognized sequence symbols.")


def _find_orfs(value: str, min_length: int, strand: str):
    value = value.upper().replace("U", "T")
    orientations = [(1, value)] if strand == "forward" else [(-1, str(Seq(value).reverse_complement()))] if strand == "reverse" else [(1, value), (-1, str(Seq(value).reverse_complement()))]
    for direction, sequence in orientations:
        for frame in range(3):
            start = None
            for offset in range(frame, len(sequence) - 2, 3):
                codon = sequence[offset : offset + 3]
                if any(base not in "ACGT" for base in codon):
                    start = None
                elif codon == "ATG" and start is None:
                    start = offset
                elif codon in {"TAA", "TAG", "TGA"}:
                    if start is not None and offset + 3 - start >= min_length:
                        a, b = (start + 1, offset + 3) if direction == 1 else (len(value) - offset - 2, len(value) - start)
                        yield Feature(start=a, end=b, strand=direction, type="ORF", label=f"ORF_{a}_{b}_{direction}")
                    start = None


def _feature_output(source_path: str, document: FeatureDocument, file: dict, records_truncated: bool = False):
    total = sum(len(record.features) for record in document.records)
    remaining = 100
    preview = []
    for record in document.records:
        copy = record.model_dump(mode="json")
        copy["features"] = copy["features"][:remaining]
        remaining = max(0, remaining - len(copy["features"]))
        preview.append(copy)
    returned = 100 - remaining
    return output({"source_path": source_path, "features_path": file["path"], "records": preview, "total": total, "returned": returned, "truncated": total > returned or records_truncated, "records_truncated": records_truncated}, file)


def _calculate(*, source: dict, max_records: int, min_length: int, strand: str, context):
    src, items, records_truncated = _records(source, max_records, context)
    sets = []
    count = 0
    for item in items:
        value = str(item.seq).upper()
        if _sequence_type(value, src.sequence_type) == "protein":
            raise ValueError("ORF detection requires DNA or RNA.")
        features = list(islice(_find_orfs(value, min_length, strand), 50001))
        count += len(features)
        if count > 50000:
            raise ValueError("More than 50000 ORFs; raise min_length or reduce input.")
        sets.append(FeatureSet(sequence_id=item.id, length=len(value), features=features))
    reference = destination(context, "reference.fasta")
    SeqIO.write(items, reference, "fasta-2line")
    reference_file = artifact(context, reference)
    document = FeatureDocument(records=sets, fasta_path=reference_file["path"])
    file = write_json(context, "features.json", document.model_dump(mode="json"))
    result = _feature_output(src.path or "inline sequence", document, file, records_truncated)
    result["files"].append(reference_file)
    return result


@bio_function_tool(timeout=120)
async def sequence_find_orfs(
    ctx: RunContextWrapper[AgentRunContext],
    source: SequenceSource,
    min_length: Annotated[int, Field(ge=3, le=2_000_000)] = 90,
    strand: Literal["forward", "reverse", "both"] = "both",
    max_records: Annotated[int, Field(ge=1, le=100)] = 100,
) -> FunctionResult[FeaturesResult]:
    """Detect ATG-to-stop ORFs with 1-based inclusive coordinates."""
    return await invoke(ctx.context, "sequence_find_orfs", _calculate, {"source": source.model_dump(mode="json"), "min_length": min_length, "strand": strand, "max_records": max_records}, FunctionResult[FeaturesResult])


__all__ = ["sequence_find_orfs", "FeatureDocument", "FeaturesResult"]
