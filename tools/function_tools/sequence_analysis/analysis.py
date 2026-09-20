"""Deterministic sequence metrics implemented by the sequence tool itself."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any


DNA_BASES = set("ACGTN")
RNA_BASES = set("ACGUN")
AA_CODES = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")
STOP_CODONS = {"TAA", "TAG", "TGA"}


def parse_fasta_text(text: str) -> list[dict[str, str]]:
    """Parse FASTA text, or treat non-header text as one sequence record."""
    records: list[dict[str, str]] = []
    current_id = "sequence_1"
    current_lines: list[str] = []
    seen_header = False

    for line in str(text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        if clean.startswith(">"):
            if seen_header or current_lines:
                records.append({"id": current_id, "sequence": "".join(current_lines).upper()})
            seen_header = True
            current_id = clean[1:].split(None, 1)[0] or f"sequence_{len(records) + 1}"
            current_lines = []
        else:
            current_lines.append(re.sub(r"\s+", "", clean))

    if seen_header or current_lines:
        records.append({"id": current_id, "sequence": "".join(current_lines).upper()})
    return records


def load_sequence_text(sequence: str | None = None, fasta_path: str | None = None) -> str:
    if fasta_path:
        return Path(fasta_path).read_text(encoding="utf-8", errors="replace")
    if sequence:
        return sequence
    raise ValueError("Provide sequence or fasta_path.")


def infer_sequence_type(sequence: str) -> str:
    letters = {char for char in sequence.upper() if char.isalpha()}
    if not letters:
        return "unknown"
    if letters <= DNA_BASES:
        return "dna"
    if letters <= RNA_BASES:
        return "rna"
    if letters <= AA_CODES:
        return "protein"
    return "mixed"


def gc_content(sequence: str) -> float | None:
    letters = [char for char in sequence.upper() if char in {"A", "C", "G", "T", "U"}]
    if not letters:
        return None
    return round(100 * sum(char in {"G", "C"} for char in letters) / len(letters), 3)


def base_counts(sequence: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in sequence.upper():
        if char.isalpha():
            counts[char] = counts.get(char, 0) + 1
    return counts


def find_orfs(sequence: str, min_length: int = 90) -> list[dict[str, Any]]:
    clean = re.sub(r"[^ACGT]", "", sequence.upper().replace("U", "T"))
    orfs: list[dict[str, Any]] = []
    for frame in range(3):
        start_index: int | None = None
        for index in range(frame, len(clean) - 2, 3):
            codon = clean[index : index + 3]
            if codon == "ATG" and start_index is None:
                start_index = index
            elif codon in STOP_CODONS and start_index is not None:
                length = index + 3 - start_index
                if length >= min_length:
                    orfs.append({
                        "frame": frame + 1,
                        "start": start_index + 1,
                        "end": index + 3,
                        "length": length,
                        "stop_codon": codon,
                    })
                start_index = None
    return orfs


def analyze_sequence_text(
    sequence: str | None = None,
    fasta_path: str | None = None,
    min_orf_length: int = 90,
) -> dict[str, Any]:
    text = load_sequence_text(sequence=sequence, fasta_path=fasta_path)
    analyses = []
    for record in parse_fasta_text(text):
        seq = record["sequence"]
        seq_type = infer_sequence_type(seq)
        analyses.append({
            "id": record["id"],
            "length": len(seq),
            "type": seq_type,
            "gc_content_percent": gc_content(seq) if seq_type in {"dna", "rna", "mixed"} else None,
            "counts": base_counts(seq),
            "orfs": find_orfs(seq, min_length=min_orf_length) if seq_type in {"dna", "rna", "mixed"} else [],
        })
    return {
        "record_count": len(analyses),
        "total_length": sum(item["length"] for item in analyses),
        "records": analyses,
    }


def global_alignment_score(
    sequence_a: str,
    sequence_b: str,
    match: int = 1,
    mismatch: int = -1,
    gap: int = -1,
) -> dict[str, Any]:
    """Return a small Needleman-Wunsch score without materializing an alignment."""
    a = re.sub(r"\s+", "", sequence_a.upper())
    b = re.sub(r"\s+", "", sequence_b.upper())
    matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        matrix[i][0] = i * gap
    for j in range(1, len(b) + 1):
        matrix[0][j] = j * gap
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            diagonal = matrix[i - 1][j - 1] + (match if a[i - 1] == b[j - 1] else mismatch)
            matrix[i][j] = max(diagonal, matrix[i - 1][j] + gap, matrix[i][j - 1] + gap)
    return {
        "sequence_a_length": len(a),
        "sequence_b_length": len(b),
        "alignment": "needleman-wunsch-score-only",
        "score": matrix[-1][-1],
        "parameters": {"match": match, "mismatch": mismatch, "gap": gap},
    }


__all__ = [
    "analyze_sequence_text",
    "base_counts",
    "find_orfs",
    "gc_content",
    "global_alignment_score",
    "infer_sequence_type",
    "load_sequence_text",
    "parse_fasta_text",
]
