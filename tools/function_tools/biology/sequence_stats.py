"""Measure bounded FASTA or inline sequence records."""
from __future__ import annotations

from io import StringIO
from itertools import islice
from typing import Annotated, Literal

from Bio import SeqIO
from Bio.Seq import Seq
from agents import RunContextWrapper
from pydantic import Field, model_validator

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import input_path, output
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.operations import invoke
from tools.infrastructure.tool_support.results import FunctionContract, FunctionResult


class SequenceSource(FunctionContract):
    sequence: str | None = Field(default=None, max_length=1_000_000, description="Inline sequence or FASTA text.")
    path: str | None = Field(default=None, description="Workspace-relative FASTA path.")
    sequence_type: Literal["auto", "dna", "rna", "protein"] = "auto"

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.sequence) == bool(self.path):
            raise ValueError("Provide exactly one of sequence or path.")
        return self


class SequenceMetric(FunctionContract):
    id: str
    length: int
    type: str
    gc_content_percent: float | None
    counts: dict[str, int]


class SequenceStats(FunctionContract):
    source_path: str
    returned: int
    truncated: bool
    records: list[SequenceMetric]


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
    raise ValueError("Unrecognized sequence symbols. Specify the sequence type and remove non-biological characters.")


def _calculate(*, source: dict, max_records: int, context):
    src, items, truncated = _records(source, max_records, context)
    result = []
    for item in items:
        value = str(item.seq).upper()
        kind = _sequence_type(value, src.sequence_type)
        counts = {symbol: value.count(symbol) for symbol in sorted(set(value))}
        called = sum(counts.get(symbol, 0) for symbol in "ACGTU")
        gc = round(100 * (counts.get("G", 0) + counts.get("C", 0)) / called, 3) if called and kind != "protein" else None
        result.append({"id": item.id, "length": len(value), "type": kind, "counts": counts, "gc_content_percent": gc})
    return output({"source_path": src.path or "inline sequence", "records": result, "returned": len(result), "truncated": truncated})


@bio_function_tool(timeout=120)
async def sequence_stats(
    ctx: RunContextWrapper[AgentRunContext],
    source: SequenceSource,
    max_records: Annotated[int, Field(ge=1, le=100)] = 100,
) -> FunctionResult[SequenceStats]:
    """Measure sequence lengths, GC among called bases, and symbol counts."""
    return await invoke(ctx.context, "sequence_stats", _calculate, {"source": source.model_dump(mode="json"), "max_records": max_records}, FunctionResult[SequenceStats])


__all__ = ["sequence_stats", "SequenceSource", "SequenceStats"]

