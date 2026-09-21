"""Bounded Biopython operations for common molecular-biology file data."""

from __future__ import annotations

from pathlib import Path
from itertools import islice
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from tools.infrastructure.tooling.context import WorkflowContext, ensure_workflow_context
from tools.infrastructure.workspace import select_workspace_file


FASTA_SUFFIXES = (".fa", ".fasta", ".fna", ".ffn", ".faa")
GENBANK_SUFFIXES = (".gb", ".gbk", ".genbank")
MAX_RECORDS = 200
MAX_SEQUENCE_CHARS = 50_000
MAX_FEATURES = 500
MAX_FILE_BYTES = 64 * 1024 * 1024


def biology_analysis(
    operation: str,
    sequence: str | None = None,
    fasta_path: str | None = None,
    genbank_path: str | None = None,
    frame: int = 1,
    max_records: int = MAX_RECORDS,
    context: WorkflowContext | None = None,
) -> dict[str, Any]:
    """Run one bounded Biopython transformation or GenBank feature read."""
    context = ensure_workflow_context(context, "biology_analysis")
    operation = str(operation or "").strip().lower()
    allowed = {"reverse_complement", "translate", "genbank_features"}
    if operation not in allowed:
        raise ValueError(f"operation must be one of: {', '.join(sorted(allowed))}.")
    limit = min(max(int(max_records), 1), MAX_RECORDS)
    if operation == "genbank_features":
        if sequence or fasta_path:
            raise ValueError("genbank_features accepts genbank_path only.")
        source, display_path = select_workspace_file(context, genbank_path, suffixes=GENBANK_SUFFIXES)
        result = _genbank_features(source, display_path, limit)
    else:
        if genbank_path:
            raise ValueError("reverse_complement and translate accept sequence or fasta_path, not genbank_path.")
        records, display_path = _records(sequence, fasta_path, context, limit)
        if operation == "reverse_complement":
            result = _reverse_complement(records, display_path)
        else:
            result = _translate(records, display_path, frame)
    return {"status": "ok", "operation": operation, **result, "summary": _summary(operation, result)}


def _records(
    sequence: str | None,
    fasta_path: str | None,
    context: WorkflowContext,
    limit: int,
) -> tuple[list[SeqRecord], str]:
    if sequence and fasta_path:
        raise ValueError("Provide sequence or fasta_path, not both.")
    if sequence:
        clean = "".join(str(sequence).split()).upper()
        if not clean:
            raise ValueError("sequence must contain biological symbols.")
        return [SeqRecord(Seq(clean), id="sequence_1", description="")], "inline sequence"
    source, display_path = select_workspace_file(context, fasta_path, suffixes=FASTA_SUFFIXES)
    _check_size(source)
    records = list(islice(SeqIO.parse(str(source), "fasta"), limit))
    if not records:
        raise ValueError(f"No FASTA records were found in {display_path}.")
    return records[:limit], display_path


def _reverse_complement(records: list[SeqRecord], source: str) -> dict[str, Any]:
    outputs = []
    for record in records:
        value = str(record.seq).upper()
        if any(char not in "ACGTUN" for char in value):
            raise ValueError("reverse_complement accepts DNA or RNA sequences only.")
        outputs.append({"id": record.id, "sequence": str(Seq(value).reverse_complement())[:MAX_SEQUENCE_CHARS]})
    return {"source_path": source, "records": outputs, "truncated": any(len(str(record.seq)) > MAX_SEQUENCE_CHARS for record in records)}


def _translate(records: list[SeqRecord], source: str, frame: int) -> dict[str, Any]:
    if frame not in {-3, -2, -1, 1, 2, 3}:
        raise ValueError("frame must be one of -3, -2, -1, 1, 2, or 3.")
    outputs = []
    for record in records:
        value = str(record.seq).upper().replace("U", "T")
        if any(char not in "ACGTN" for char in value):
            raise ValueError("translate accepts DNA or RNA sequences only.")
        if frame < 0:
            value = str(Seq(value).reverse_complement())
        coding = value[abs(frame) - 1 :]
        usable_length = len(coding) - (len(coding) % 3)
        translated = str(Seq(coding[:usable_length]).translate(to_stop=False))
        outputs.append({
            "id": record.id,
            "frame": frame,
            "protein": translated[:MAX_SEQUENCE_CHARS],
            "trimmed_bases": len(coding) - usable_length,
        })
    return {"source_path": source, "records": outputs, "truncated": any(len(str(record.seq)) > MAX_SEQUENCE_CHARS * 3 for record in records)}


def _genbank_features(source: Path, display_path: str, limit: int) -> dict[str, Any]:
    _check_size(source)
    records = list(islice(SeqIO.parse(str(source), "genbank"), limit))
    if not records:
        raise ValueError(f"No GenBank records were found in {display_path}.")
    features = []
    for record in records[:limit]:
        for feature in record.features:
            if len(features) >= MAX_FEATURES:
                break
            qualifiers = {
                str(key): [str(value) for value in (values if isinstance(values, list) else [values])[:5]]
                for key, values in feature.qualifiers.items()
            }
            features.append({
                "record_id": record.id,
                "type": str(feature.type),
                "start": int(feature.location.start) + 1 if feature.location else None,
                "end": int(feature.location.end) if feature.location else None,
                "strand": feature.location.strand if feature.location else None,
                "qualifiers": qualifiers,
            })
    return {
        "source_path": display_path,
        "record_count": min(len(records), limit),
        "sequence_lengths": [{"id": record.id, "length": len(record.seq)} for record in records[:limit]],
        "feature_count": len(features),
        "features": features,
        "truncated": len(features) >= MAX_FEATURES,
    }


def _check_size(source: Path) -> None:
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Biology files are limited to 64 MB for bounded parsing.")


def _summary(operation: str, result: dict[str, Any]) -> str:
    source = result.get("source_path", "the supplied data")
    if operation == "genbank_features":
        return f"Read {result.get('feature_count', 0)} GenBank feature(s) from {source}."
    return f"Completed {operation.replace('_', ' ')} for {result.get('record_count', len(result.get('records', [])))} record(s) from {source}."


__all__ = ["biology_analysis"]
