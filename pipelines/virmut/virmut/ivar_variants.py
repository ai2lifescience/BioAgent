"""FASTQ read alignment and iVar variant calling."""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
_PAIR_RE = re.compile(r"^(?P<sample>.+?)(?:_R|_)(?P<read>[12])(?P<tail>(?:[_-].*)?)$")
_REQUIRED_IVAR_COLUMNS = (
    "REGION",
    "POS",
    "REF",
    "ALT",
    "ALT_DP",
    "REF_DP",
    "TOTAL_DP",
    "ALT_FREQ",
    "ALT_QUAL",
    "PVAL",
    "PASS",
)
_SNP_BASES = {"A", "C", "G", "T", "N"}


@dataclass(frozen=True)
class IvarVariant:
    region: str
    pos: int
    ref: str
    alt: str
    alt_depth: str
    ref_depth: str
    total_depth: str
    alt_freq: str
    alt_qual: str
    pval: str
    pass_filter: str


def run_fastq_pipeline(
    reference: Path,
    fastq_dir: Path,
    output_dir: Path,
    threads: int = 1,
) -> tuple[dict[str, Path], dict[str, dict[int, IvarVariant]]]:
    """Run minimap2, samtools, and iVar for every FASTQ sample."""
    if threads <= 0:
        raise ValueError("threads must be positive")

    reference = Path(reference)
    output_dir = Path(output_dir)
    read_sets = _detect_pairs(Path(fastq_dir))

    snp_tsvs: dict[str, Path] = {}
    sample_variants: dict[str, dict[int, IvarVariant]] = {}
    for sample, reads in read_sets.items():
        output_sam = output_dir / "align" / f"{sample}.sam"
        output_bam = output_dir / "align" / f"{sample}.bam"
        output_prefix = output_dir / "ivar" / sample
        ivar_tsv = output_prefix.parent / f"{output_prefix.name}.tsv"
        output_snp_tsv = output_dir / "snps" / f"{sample}.tsv"

        _run_minimap2_short_reads(
            reference=reference,
            reads=reads,
            output_sam=output_sam,
            threads=threads,
        )
        _run_samtools_sort(
            input_sam=output_sam,
            output_bam=output_bam,
            threads=threads,
        )
        _run_samtools_index(output_bam)
        _run_ivar_variants(
            reference=reference,
            input_bam=output_bam,
            output_prefix=output_prefix,
        )

        variants = _parse_ivar_records(ivar_tsv)
        _write_snp_tsv(variants, output_snp_tsv)
        snp_tsvs[sample] = output_snp_tsv
        sample_variants[sample] = variants

    return snp_tsvs, sample_variants


def parse_ivar_tsv(tsv_path: Path) -> dict[str, dict[int, IvarVariant]]:
    """Parse one iVar variants TSV into a sample-indexed variant mapping."""
    tsv_path = Path(tsv_path)
    return {tsv_path.stem: _parse_ivar_records(tsv_path)}


def _parse_ivar_records(tsv_path: Path) -> dict[int, IvarVariant]:
    """Parse one iVar variants TSV into position-indexed variant calls."""
    variants: dict[int, IvarVariant] = {}
    with Path(tsv_path).open(encoding="utf-8", newline="") as tsv_file:
        reader = csv.DictReader(tsv_file, delimiter="\t")
        fieldnames = set(reader.fieldnames or [])
        missing = [column for column in _REQUIRED_IVAR_COLUMNS if column not in fieldnames]
        if missing:
            raise ValueError("iVar TSV missing required columns: " + ", ".join(missing))

        for row in reader:
            if not row.get("POS"):
                continue
            variant = IvarVariant(
                region=_value(row, "REGION"),
                pos=int(_value(row, "POS")),
                ref=_value(row, "REF").upper(),
                alt=_value(row, "ALT").upper(),
                alt_depth=_value(row, "ALT_DP"),
                ref_depth=_value(row, "REF_DP"),
                total_depth=_value(row, "TOTAL_DP"),
                alt_freq=_value(row, "ALT_FREQ"),
                alt_qual=_value(row, "ALT_QUAL"),
                pval=_value(row, "PVAL"),
                pass_filter=_value(row, "PASS"),
            )
            existing = variants.get(variant.pos)
            if existing is None or _variant_rank(variant) > _variant_rank(existing):
                variants[variant.pos] = variant

    return variants


def _detect_pairs(fastq_dir: Path) -> dict[str, tuple[Path, ...]]:
    """Group complete _R1/_R2 pairs and leave other FASTQs as single-end."""
    fastq_dir = Path(fastq_dir)
    if not fastq_dir.is_dir():
        raise ValueError("FASTQ input must be a directory")

    fastqs = [
        path
        for path in sorted(fastq_dir.iterdir())
        if path.is_file() and _is_fastq(path)
    ]
    if not fastqs:
        raise ValueError("no FASTQ reads")

    pair_candidates: dict[tuple[str, str], dict[str, Path]] = {}
    for path in fastqs:
        stem = _strip_fastq_suffix(path.name)
        match = _PAIR_RE.match(stem)
        if match is None:
            continue
        key = (match.group("sample"), match.group("tail") or "")
        pair_candidates.setdefault(key, {})[match.group("read")] = path

    read_sets: dict[str, tuple[Path, ...]] = {}
    paired_paths: set[Path] = set()
    for (sample, _tail), mates in sorted(pair_candidates.items()):
        if "1" not in mates or "2" not in mates:
            continue
        _add_read_set(read_sets, sample, (mates["1"], mates["2"]))
        paired_paths.update(mates.values())

    for path in fastqs:
        if path in paired_paths:
            continue
        sample = _strip_fastq_suffix(path.name)
        _add_read_set(read_sets, sample, (path,))

    return read_sets


def _run_minimap2_short_reads(
    reference: Path,
    reads: tuple[Path, ...],
    output_sam: Path,
    threads: int,
) -> None:
    output_sam = Path(output_sam)
    output_sam.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "minimap2",
        "-ax",
        "sr",
        "-t",
        str(threads),
        str(reference),
        *[str(read) for read in reads],
    ]
    with output_sam.open("w", encoding="utf-8") as sam_file:
        subprocess.run(cmd, stdout=sam_file, check=True)


def _run_samtools_sort(input_sam: Path, output_bam: Path, threads: int) -> None:
    output_bam = Path(output_bam)
    output_bam.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "samtools",
            "sort",
            "-@",
            str(threads),
            str(input_sam),
            "-o",
            str(output_bam),
        ],
        check=True,
    )


def _run_samtools_index(output_bam: Path) -> None:
    subprocess.run(["samtools", "index", str(output_bam)], check=True)


def _run_ivar_variants(
    reference: Path,
    input_bam: Path,
    output_prefix: Path,
) -> None:
    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    mpileup_cmd = [
        "samtools",
        "mpileup",
        "-aa",
        "-A",
        "-d",
        "0",
        "-Q",
        "20",
        "-q",
        "30",
        "-f",
        str(reference),
        str(input_bam),
    ]
    ivar_cmd = [
        "ivar",
        "variants",
        "-p",
        str(output_prefix),
        "-q",
        "20",
        "-t",
        "0.03",
        "-m",
        "10",
        "-r",
        str(reference),
    ]

    mpileup = subprocess.Popen(mpileup_cmd, stdout=subprocess.PIPE)
    try:
        if mpileup.stdout is None:
            raise RuntimeError("samtools mpileup stdout pipe was not created")
        subprocess.run(ivar_cmd, stdin=mpileup.stdout, check=True)
        mpileup.stdout.close()
        return_code = mpileup.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, mpileup_cmd)
    except Exception:
        if mpileup.stdout is not None and not mpileup.stdout.closed:
            mpileup.stdout.close()
        if mpileup.poll() is None:
            mpileup.kill()
        mpileup.wait()
        raise


def _write_snp_tsv(
    variants: dict[int, IvarVariant],
    output_tsv: Path,
) -> None:
    output_tsv = Path(output_tsv)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with output_tsv.open("w", encoding="utf-8") as out:
        out.write("pos\tref\talt\n")
        for pos, variant in sorted(variants.items()):
            if _is_snp(variant):
                out.write(f"{pos}\t{variant.ref}\t{variant.alt}\n")


def _is_fastq(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in _FASTQ_SUFFIXES)


def _strip_fastq_suffix(filename: str) -> str:
    lower = filename.lower()
    for suffix in _FASTQ_SUFFIXES:
        if lower.endswith(suffix):
            return filename[: -len(suffix)]
    return Path(filename).stem


def _add_read_set(
    read_sets: dict[str, tuple[Path, ...]],
    sample: str,
    reads: tuple[Path, ...],
) -> None:
    if sample in read_sets:
        raise ValueError(f"duplicate FASTQ sample name: {sample}")
    read_sets[sample] = reads


def _value(row: dict[str, str | None], column: str) -> str:
    return (row.get(column) or "NA").strip() or "NA"


def _variant_rank(variant: IvarVariant) -> tuple[float, int]:
    return (_as_float(variant.alt_freq), _as_int(variant.alt_depth))


def _is_snp(variant: IvarVariant) -> bool:
    return (
        len(variant.ref) == 1
        and len(variant.alt) == 1
        and variant.ref in _SNP_BASES
        and variant.alt in _SNP_BASES
        and variant.ref != variant.alt
    )


def _as_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return -1.0


def _as_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return -1
