"""Reverse-complement bounded nucleotide records into a FASTA artifact."""
from __future__ import annotations

from io import StringIO
from itertools import islice
from typing import Annotated, Literal

from Bio import SeqIO
from Bio.Seq import Seq
from agents import RunContextWrapper
from pydantic import Field, model_validator

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.artifacts import artifact, destination, input_path, output
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


class Complement(FunctionContract):
    id: str
    sequence: str
    type: str
    length: int


class ComplementResult(FunctionContract):
    source_path: str
    sequence_path: str
    records: list[Complement]
    returned: int
    truncated: bool


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


def _calculate(*, source: dict, max_records: int, context):
    src, items, truncated = _records(source, max_records, context)
    records, fasta = [], []
    for item in items:
        value = str(item.seq).upper()
        kind = _sequence_type(value, src.sequence_type)
        if kind == "protein":
            raise ValueError("Reverse complement requires DNA or RNA.")
        seq = Seq(value)
        complement = str(seq.reverse_complement_rna() if kind == "rna" else seq.reverse_complement())
        fasta.append(f">{item.id}\n{complement}\n")
        records.append({"id": item.id, "sequence": complement[:500], "type": kind, "length": len(complement)})
        truncated |= len(complement) > 500
    target = destination(context, "reverse_complement.fna")
    target.write_text("".join(fasta), encoding="utf-8")
    file = artifact(context, target)
    return output({"source_path": src.path or "inline sequence", "sequence_path": file["path"], "records": records, "returned": len(records), "truncated": truncated}, file)


@bio_function_tool(timeout=120)
async def sequence_reverse_complement(
    ctx: RunContextWrapper[AgentRunContext],
    source: SequenceSource,
    max_records: Annotated[int, Field(ge=1, le=100)] = 100,
) -> FunctionResult[ComplementResult]:
    """Reverse-complement DNA or RNA records, preserving ambiguous bases and RNA U."""
    return await invoke(ctx.context, "sequence_reverse_complement", _calculate, {"source": source.model_dump(mode="json"), "max_records": max_records}, FunctionResult[ComplementResult])


__all__ = ["sequence_reverse_complement", "ComplementResult"]
