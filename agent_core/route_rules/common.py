"""Shared helpers for deterministic route rules."""

from __future__ import annotations

import re


def extract_labeled_value(text: str, label: str) -> str | None:
    quoted = re.search(
        rf"\b{re.escape(label)}\b\s*(?::|=)?\s*(['\"])(.+?)\1",
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        return quoted.group(2).strip()

    bare = re.search(
        rf"\b{re.escape(label)}\b\s*(?::|=)?\s*([A-Za-z0-9_./ -]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not bare:
        return None
    value = re.split(r"\b(?:and|with|tag|message|uppercase)\b", bare.group(1), maxsplit=1)[0]
    return value.strip(" .,:;") or None


def extract_quoted_or_labeled_path(text: str) -> str | None:
    quoted = re.search(
        r"\b(?:file|path|input_path|input|fasta|fastq|fq|csv|tsv|structure|pdb|cif|mmcif|genbank|gbk|gff|genome|bam|sam|bed|vcf)\b\s*(?::|=)?\s*(['\"])(.+?)\1",
        text,
        re.IGNORECASE,
    )
    if quoted:
        return quoted.group(2).strip()
    bare = re.search(
        r"([A-Za-z0-9_./-]+\.(?:genbank|fasta|fastq|gff3|mmcif|bcif|gbk|fna|faa|fq|gff|csv|tsv|txt|cif|pdb|svg|fa|gb|md|bam|bai|sam|bed|vcf|gz|bgz|zip))",
        text,
        re.IGNORECASE,
    )
    return bare.group(1) if bare else None


def extract_sequence(text: str) -> str | None:
    fasta = re.search(r"(>[^\\n]+\\n[\\sA-Za-z*.-]+)", text)
    if fasta:
        return fasta.group(1).strip()
    quoted = re.search(
        r"\b(?:sequence|seq)\b\s*(?::|=)?\s*(['\"])(.+?)\1",
        text,
        re.IGNORECASE,
    )
    if quoted:
        return re.sub(r"\s+", "", quoted.group(2)).strip()
    labeled = re.search(
        r"\b(?:sequence|seq)\b\s*(?::|=)?\s*([A-Za-z*.-]{8,}(?:\s+[A-Za-z*.-]{3,})*)",
        text,
        re.IGNORECASE,
    )
    if labeled:
        value = re.split(
            r"\b(?:with|using|against|database|db|program|blastn|blastp|blastx|"
            r"tblastn|tblastx|wait|poll|return|show|results?|hits?|top)\b",
            labeled.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return re.sub(r"\s+", "", value).strip()
    standalone = re.search(r"\b([ACGTRYSWKMBDHVNU]{12,})\b", text, re.IGNORECASE)
    return standalone.group(1).upper() if standalone else None
