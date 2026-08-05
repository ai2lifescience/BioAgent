"""FASTQ discovery, short-read alignment, and bcftools variant calling."""

from __future__ import annotations

import logging
import re
import subprocess
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .reference import ReferenceGenome


LOGGER = logging.getLogger(__name__)
FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
PAIR_RE = re.compile(
    r"^(?P<sample>.+?)(?:_R|_)(?P<read>[12])(?P<tail>(?:[_-].*)?)$",
    re.IGNORECASE,
)
CANONICAL = frozenset("ACGT")


@dataclass(frozen=True)
class BcftoolsVariant:
    region: str
    pos: int
    global_pos: int
    variant_type: str
    ref: str
    alt: str
    evidence: str
    ftype: str
    strand: str
    nt_pos: str
    aa_pos: str
    locus_tag: str
    gene: str
    product: str
    effect: str
    alt_freq: str
    depth: str
    pval: str = "NA"
    pass_filter: str = "TRUE"


@dataclass
class SampleCalls:
    name: str
    reads: Tuple[Path, ...]
    output_dir: Path
    variants: Dict[int, str] = field(default_factory=dict)
    variant_info: Dict[int, BcftoolsVariant] = field(default_factory=dict)
    intervals: List[Tuple[int, int]] = field(default_factory=list)
    _starts: List[int] = field(default_factory=list, init=False, repr=False)

    def finalize_intervals(self) -> None:
        merged: List[Tuple[int, int]] = []
        for start, end in sorted(self.intervals):
            if start >= end:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        self.intervals = merged
        self._starts = [start for start, _ in merged]

    def is_covered(self, position: int) -> bool:
        index = bisect_right(self._starts, position) - 1
        return index >= 0 and position < self.intervals[index][1]

    def base_at(self, position: int, reference_base: str) -> str:
        if position in self.variants:
            return self.variants[position]
        return reference_base if self.is_covered(position) else "N"


def _detect_pairs(fastq_dir: Path) -> Dict[str, Tuple[Path, ...]]:
    """Group _R1/_R2 and _1/_2 mates, leaving unmatched files single-end."""
    fastq_dir = Path(fastq_dir)
    if not fastq_dir.is_dir():
        raise ValueError(f"FASTQ input must be a directory: {fastq_dir}")
    fastqs = [
        path
        for path in sorted(fastq_dir.iterdir())
        if path.is_file() and _is_fastq(path)
    ]
    if not fastqs:
        raise ValueError(f"No FASTQ files found in {fastq_dir}")

    candidates: Dict[Tuple[str, str], Dict[str, Path]] = {}
    for path in fastqs:
        match = PAIR_RE.match(_strip_fastq_suffix(path.name))
        if match is None:
            continue
        key = (match.group("sample"), match.group("tail") or "")
        candidates.setdefault(key, {})[match.group("read")] = path

    read_sets: Dict[str, Tuple[Path, ...]] = {}
    paired_paths = set()
    for (sample, _tail), mates in sorted(candidates.items()):
        if "1" not in mates or "2" not in mates:
            continue
        _add_read_set(read_sets, sample, (mates["1"], mates["2"]))
        paired_paths.update(mates.values())

    for path in fastqs:
        if path in paired_paths:
            continue
        _add_read_set(read_sets, _strip_fastq_suffix(path.name), (path,))
    return read_sets


def run_fastq_pipeline(
    reference: ReferenceGenome,
    fastq_dir: Path,
    output_dir: Path,
    threads: int = 1,
) -> List[SampleCalls]:
    """Run minimap2, samtools, and bcftools for every detected sample."""
    if type(threads) is not int or threads < 1:
        raise ValueError("threads must be an integer >= 1")
    read_sets = _detect_pairs(Path(fastq_dir))
    calls_root = Path(output_dir) / "bcftools"
    calls_root.mkdir(parents=True, exist_ok=True)

    samples: List[SampleCalls] = []
    for sample_name, reads in read_sets.items():
        sample_dir = calls_root / sample_name
        _run_bcftools_pipeline(reference.path, reads, sample_dir, threads)
        variant_info = parse_bcftools_vcf(sample_dir / "variants.vcf", reference)
        sample = SampleCalls(
            name=sample_name,
            reads=reads,
            output_dir=sample_dir,
            variants={position: variant.alt for position, variant in variant_info.items()},
            variant_info=variant_info,
            intervals=_covered_intervals_from_bam(sample_dir / "aligned.bam", reference),
        )
        sample.finalize_intervals()
        samples.append(sample)
        LOGGER.info("bcftools variant calling completed for %s", sample_name)
    return samples


def _covered_intervals_from_bam(
    bam_path: Path,
    reference: ReferenceGenome,
) -> List[Tuple[int, int]]:
    """Return half-open reference intervals with positive read depth."""
    command = ["samtools", "depth", str(bam_path)]
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
    intervals: List[Tuple[int, int]] = []
    current_start: Optional[int] = None
    current_end: Optional[int] = None
    try:
        for line_number, raw_line in enumerate(process.stdout, 1):
            if not raw_line.strip():
                continue
            fields = raw_line.rstrip("\n").split("\t")
            if len(fields) < 3:
                raise ValueError(f"Malformed samtools depth record at line {line_number}")
            region, pos_text, depth_text = fields[:3]
            if region not in reference.records:
                raise ValueError(f"samtools depth refers to unknown reference record: {region}")
            try:
                local_pos = int(pos_text)
                depth = int(depth_text)
            except ValueError as error:
                raise ValueError(f"Malformed samtools depth record at line {line_number}") from error
            if depth <= 0:
                continue
            if local_pos < 1 or local_pos > len(reference.records[region]):
                raise ValueError(f"samtools depth position outside reference record: {region}:{local_pos}")
            global_pos = reference.offsets[region] + local_pos - 1
            if current_start is None or current_end is None:
                current_start = global_pos
                current_end = global_pos + 1
            elif global_pos <= current_end:
                current_end = max(current_end, global_pos + 1)
            else:
                intervals.append((current_start, current_end))
                current_start = global_pos
                current_end = global_pos + 1
        stderr = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    if return_code != 0:
        detail = stderr.strip()
        raise RuntimeError(
            f"samtools depth failed for {bam_path} with code {return_code}: {detail}"
        )
    if current_start is not None and current_end is not None:
        intervals.append((current_start, current_end))
    return intervals


def parse_bcftools_vcf(
    vcf_path: Path,
    reference: ReferenceGenome,
) -> Dict[int, BcftoolsVariant]:
    """Parse genotype-supported SNP calls from a bcftools VCF."""
    variants: Dict[int, BcftoolsVariant] = {}
    header_seen = False
    with Path(vcf_path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip() or raw_line.startswith("##"):
                continue
            if raw_line.startswith("#CHROM"):
                columns = raw_line.rstrip("\n").split("\t")
                if len(columns) < 10:
                    raise ValueError("bcftools VCF must contain one sample column")
                header_seen = True
                continue
            if raw_line.startswith("#"):
                continue
            if not header_seen:
                raise ValueError("bcftools VCF is missing the #CHROM header")

            fields = raw_line.rstrip("\n").split("\t")
            if len(fields) < 10:
                raise ValueError(f"Malformed VCF record at {vcf_path}:{line_number}")
            region, pos_text, _identifier, ref, alt_text, _qual, filter_value, info_text, format_text, sample_text = fields[:10]
            if region not in reference.records:
                raise ValueError(f"bcftools VCF refers to unknown reference record: {region}")
            pos = int(pos_text)
            if pos < 1 or pos > len(reference.records[region]):
                raise ValueError(f"bcftools position outside reference record: {region}:{pos}")

            format_values = _parse_format(format_text, sample_text)
            alt_index = _called_alt_index(format_values.get("GT", "."), format_values.get("AD", ""))
            if alt_index is None:
                continue
            alternate_alleles = alt_text.upper().split(",")
            if alt_index > len(alternate_alleles):
                continue
            ref = ref.upper()
            alt = alternate_alleles[alt_index - 1]
            if not _is_snp_allele(ref, alt):
                continue

            info_values = _parse_info(info_text)
            ad = format_values.get("AD") or info_values.get("AD", "")
            alt_freq, depth = _vcf_metrics(ad, alt_index)
            if depth == "NA":
                depth = format_values.get("DP") or info_values.get("DP", "NA")
            global_pos = reference.offsets[region] + pos - 1
            variant = BcftoolsVariant(
                region=region,
                pos=pos,
                global_pos=global_pos,
                variant_type="SNP",
                ref=ref,
                alt=alt,
                evidence=f"AD={ad or 'NA'};DP={depth}",
                ftype="NA",
                strand="+",
                nt_pos="NA",
                aa_pos="NA",
                locus_tag="NA",
                gene="NA",
                product="NA",
                effect="NA",
                alt_freq=alt_freq,
                depth=depth,
                pass_filter="TRUE" if filter_value in {"PASS", "."} else "FALSE",
            )
            existing = variants.get(global_pos)
            if existing is None or _variant_rank(variant) > _variant_rank(existing):
                variants[global_pos] = variant
    if not header_seen:
        raise ValueError("bcftools VCF is missing the #CHROM header")
    return variants


def _run_bcftools_pipeline(
    reference: Path,
    reads: Sequence[Path],
    sample_dir: Path,
    threads: int,
) -> None:
    if len(reads) not in {1, 2}:
        raise ValueError("Variant calling requires one single-end read or one paired-end read set")
    sample_dir = Path(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)
    output_sam = sample_dir / "aligned.sam"
    output_bam = sample_dir / "aligned.bam"
    output_vcf = sample_dir / "variants.vcf"

    minimap2_command = [
        "minimap2",
        "-ax",
        "sr",
        "-t",
        str(threads),
        str(reference),
        *[str(read) for read in reads],
    ]
    LOGGER.debug("Running: %s", " ".join(minimap2_command))
    with output_sam.open("w", encoding="ascii") as sam_file:
        subprocess.run(minimap2_command, stdout=sam_file, check=True)

    subprocess.run(
        ["samtools", "sort", str(output_sam), "-o", str(output_bam)],
        check=True,
    )
    subprocess.run(["samtools", "index", str(output_bam)], check=True)

    mpileup_command = [
        "bcftools",
        "mpileup",
        "-a",
        "AD,DP",
        "-Q",
        "20",
        "-q",
        "30",
        "-f",
        str(reference),
        str(output_bam),
    ]
    call_command = [
        "bcftools",
        "call",
        "-mv",
        "-Ov",
        "-o",
        str(output_vcf),
    ]
    mpileup = subprocess.Popen(mpileup_command, stdout=subprocess.PIPE)
    try:
        if mpileup.stdout is None:
            raise RuntimeError("bcftools mpileup stdout pipe was not created")
        subprocess.run(call_command, stdin=mpileup.stdout, check=True)
        mpileup.stdout.close()
        return_code = mpileup.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, mpileup_command)
    except Exception:
        if mpileup.stdout is not None and not mpileup.stdout.closed:
            mpileup.stdout.close()
        if mpileup.poll() is None:
            mpileup.kill()
        mpileup.wait()
        raise


def _parse_format(format_text: str, sample_text: str) -> Dict[str, str]:
    keys = format_text.split(":")
    values = sample_text.split(":")
    return dict(zip(keys, values))


def _parse_info(info_text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in info_text.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def _called_alt_index(genotype: str, ad: str) -> Optional[int]:
    allele_indexes = {
        int(value)
        for value in re.split(r"[/|]", genotype)
        if value.isdigit() and int(value) > 0
    }
    if not allele_indexes:
        return None
    depths = _parse_ad(ad)
    return max(
        allele_indexes,
        key=lambda index: depths[index] if index < len(depths) else -1,
    )


def _vcf_metrics(ad: str, alt_index: int = 1) -> Tuple[str, str]:
    depths = _parse_ad(ad)
    if not depths or alt_index >= len(depths):
        return "NA", "NA"
    ref_depth = depths[0]
    alt_depth = depths[alt_index]
    total_depth = ref_depth + alt_depth
    if total_depth == 0:
        return "NA", "0"
    frequency = f"{alt_depth / total_depth:.6f}".rstrip("0").rstrip(".")
    return frequency, str(total_depth)


def _parse_ad(ad: str) -> List[int]:
    if not ad or ad == ".":
        return []
    try:
        return [int(value) if value != "." else 0 for value in ad.split(",")]
    except ValueError:
        return []


def _variant_rank(variant: BcftoolsVariant) -> Tuple[float, int]:
    try:
        frequency = float(variant.alt_freq)
    except ValueError:
        frequency = -1.0
    try:
        depth = int(variant.depth)
    except ValueError:
        depth = -1
    return frequency, depth


def _is_snp_allele(ref: str, alt: str) -> bool:
    return (
        len(ref) == 1
        and len(alt) == 1
        and ref in CANONICAL
        and alt in CANONICAL
        and ref != alt
    )


def _is_fastq(path: Path) -> bool:
    return any(path.name.lower().endswith(suffix) for suffix in FASTQ_SUFFIXES)


def _strip_fastq_suffix(filename: str) -> str:
    lower = filename.lower()
    for suffix in FASTQ_SUFFIXES:
        if lower.endswith(suffix):
            return filename[: -len(suffix)]
    return Path(filename).stem


def _add_read_set(
    read_sets: Dict[str, Tuple[Path, ...]],
    sample: str,
    reads: Tuple[Path, ...],
) -> None:
    sample = re.sub(r"\s+", "_", sample.strip())
    if not sample:
        raise ValueError("FASTQ sample name is empty")
    if sample in read_sets:
        raise ValueError(f"Duplicate FASTQ sample name: {sample}")
    read_sets[sample] = reads
