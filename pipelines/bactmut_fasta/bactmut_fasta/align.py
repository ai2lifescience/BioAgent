"""Genome alignment backends and SNP extraction."""

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .fasta import load_fasta
from .models import ReferenceGenome, SampleCalls


LOGGER = logging.getLogger(__name__)
CIGAR_RE = re.compile(r"(\d+)([MIDNSHP=X])")
CANONICAL = frozenset("ACGT")


def load_reference(path: Path) -> ReferenceGenome:
    records_list = load_fasta(path)
    records: Dict[str, str] = {}
    offsets: Dict[str, int] = {}
    offset = 0
    for name, sequence in records_list:
        if name in records:
            raise ValueError(f"Duplicate reference record name: {name}")
        records[name] = sequence
        offsets[name] = offset
        offset += len(sequence)
    return ReferenceGenome(path=path, records=records, offsets=offsets, length=offset)


def choose_alignment_backend(requested: str) -> str:
    if requested == "minimap2":
        if not shutil.which("minimap2"):
            raise RuntimeError("--aligner minimap2 was requested, but minimap2 is not on PATH")
        return "minimap2"
    if requested == "internal":
        return "internal"
    return "minimap2" if shutil.which("minimap2") else "internal"


def align_sample(
    reference: ReferenceGenome,
    query_path: Path,
    sample_name: str,
    backend: str,
    threads: int,
) -> SampleCalls:
    if backend == "minimap2":
        return _align_minimap2(reference, query_path, sample_name, threads)
    return _align_internal(reference, query_path, sample_name)


def _record_call(calls: SampleCalls, position: int, ref_base: str, query_base: str) -> None:
    query_base = query_base.upper()
    if query_base in CANONICAL:
        if query_base != ref_base:
            existing = calls.variants.get(position)
            calls.variants[position] = query_base if existing in (None, query_base) else "N"
    elif query_base != ref_base:
        existing = calls.ambiguous.get(position)
        calls.ambiguous[position] = query_base if existing in (None, query_base) else "N"


def _align_internal(
    reference: ReferenceGenome, query_path: Path, sample_name: str
) -> SampleCalls:
    query_records = load_fasta(query_path)
    calls = SampleCalls(name=sample_name, path=query_path)
    if len(reference.records) != len(query_records):
        raise RuntimeError(
            f"Internal aligner only supports equally structured, full-length genomes; "
            f"{query_path.name} has {len(query_records)} record(s), reference has "
            f"{len(reference.records)}. Install minimap2 for contig assemblies."
        )
    for (ref_name, ref_sequence), (query_name, query_sequence) in zip(
        reference.records.items(), query_records
    ):
        if len(ref_sequence) != len(query_sequence):
            raise RuntimeError(
                f"Internal aligner requires equal sequence lengths ({query_path.name}: "
                f"{len(query_sequence)}, reference record {ref_name}: {len(ref_sequence)}). "
                "Install minimap2 for assemblies with indels or contigs."
            )
        offset = reference.offsets[ref_name]
        calls.intervals.append((offset, offset + len(ref_sequence)))
        for local_position, (ref_base, query_base) in enumerate(
            zip(ref_sequence, query_sequence)
        ):
            _record_call(calls, offset + local_position, ref_base, query_base)
    calls.finalize_intervals()
    return calls


def _align_minimap2(
    reference: ReferenceGenome,
    query_path: Path,
    sample_name: str,
    threads: int,
) -> SampleCalls:
    command = [
        "minimap2",
        "-a",
        "--eqx",
        "-x",
        "asm5",
        "-t",
        str(max(1, threads)),
        str(reference.path),
        str(query_path),
    ]
    LOGGER.debug("Running: %s", " ".join(command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="ascii",
        errors="replace",
    )
    assert process.stdout is not None
    calls = SampleCalls(name=sample_name, path=query_path)
    try:
        for line in process.stdout:
            if line.startswith("@"):
                continue
            _parse_sam_alignment(line, reference, calls)
        stderr = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        raise
    if return_code != 0:
        raise RuntimeError(
            f"minimap2 failed for {query_path.name} (exit {return_code}): {stderr.strip()}"
        )
    calls.finalize_intervals()
    return calls


def _parse_sam_alignment(
    line: str, reference: ReferenceGenome, calls: SampleCalls
) -> None:
    fields = line.rstrip("\n").split("\t")
    if len(fields) < 11:
        raise RuntimeError("Malformed SAM output from minimap2")
    flag = int(fields[1])
    if flag & (0x4 | 0x100):  # unmapped or secondary; supplementary mappings are useful
        return
    reference_name = fields[2]
    if reference_name not in reference.records:
        raise RuntimeError(f"SAM refers to unknown reference record: {reference_name}")
    reference_sequence = reference.records[reference_name]
    reference_position = int(fields[3]) - 1
    query_position = 0
    query_sequence = fields[9].upper()
    global_offset = reference.offsets[reference_name]
    for length_text, operation in CIGAR_RE.findall(fields[5]):
        length = int(length_text)
        if operation in ("M", "=", "X"):
            start = reference_position
            end = reference_position + length
            if end > len(reference_sequence) or query_position + length > len(query_sequence):
                raise RuntimeError("CIGAR extends beyond sequence bounds")
            calls.intervals.append((global_offset + start, global_offset + end))
            ref_chunk = reference_sequence[start:end]
            query_chunk = query_sequence[query_position : query_position + length]
            if operation != "=" or any(base not in CANONICAL for base in query_chunk):
                for index, (ref_base, query_base) in enumerate(zip(ref_chunk, query_chunk)):
                    if ref_base != query_base:
                        _record_call(
                            calls, global_offset + start + index, ref_base, query_base
                        )
            reference_position = end
            query_position += length
        elif operation in ("I", "S"):
            query_position += length
        elif operation in ("D", "N"):
            reference_position += length
        elif operation in ("H", "P"):
            continue
        else:
            raise RuntimeError(f"Unsupported CIGAR operation: {operation}")

