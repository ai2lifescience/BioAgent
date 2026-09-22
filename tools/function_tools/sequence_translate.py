"""Translate bounded nucleotide records into a FASTA artifact."""
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


class Translation(FunctionContract):
    id: str
    frame: int
    protein: str
    trimmed_bases: int
    total_residues: int


class TranslationResult(FunctionContract):
    source_path: str
    sequence_path: str
    records: list[Translation]
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


def _calculate(*, source: dict, frame: int, genetic_code: int, max_records: int, context):
    src, items, truncated = _records(source, max_records, context)
    translations, fasta = [], []
    for item in items:
        value = str(item.seq).upper()
        if _sequence_type(value, src.sequence_type) == "protein":
            raise ValueError("Translation requires DNA or RNA.")
        coding = Seq(value.replace("U", "T"))
        if frame < 0:
            coding = coding.reverse_complement()
        coding = coding[abs(frame) - 1 :]
        trim = len(coding) % 3
        protein = str(coding[: len(coding) - trim].translate(table=genetic_code))
        fasta.append(f">{item.id}\n{protein}\n")
        translations.append({"id": item.id, "frame": frame, "protein": protein[:500], "trimmed_bases": trim, "total_residues": len(protein)})
        truncated |= len(protein) > 500
    target = destination(context, "translation.faa")
    target.write_text("".join(fasta), encoding="utf-8")
    file = artifact(context, target)
    return output({"source_path": src.path or "inline sequence", "sequence_path": file["path"], "records": translations, "returned": len(translations), "truncated": truncated}, file)


@bio_function_tool(timeout=120)
async def sequence_translate(
    ctx: RunContextWrapper[AgentRunContext],
    source: SequenceSource,
    frame: Literal[-3, -2, -1, 1, 2, 3] = 1,
    genetic_code: Annotated[int, Field(ge=1, le=33)] = 1,
    max_records: Annotated[int, Field(ge=1, le=100)] = 100,
) -> FunctionResult[TranslationResult]:
    """Translate nucleotide records in one frame and genetic code."""
    return await invoke(ctx.context, "sequence_translate", _calculate, {"source": source.model_dump(mode="json"), "frame": frame, "genetic_code": genetic_code, "max_records": max_records}, FunctionResult[TranslationResult])


__all__ = ["sequence_translate", "TranslationResult"]

