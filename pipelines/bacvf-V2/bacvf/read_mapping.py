"""Direct short-read mapping against the deployed nucleotide gene database."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .command import CommandRunner
from .config import PipelineConfig
from .errors import ParseError


def reference_sequences(config: PipelineConfig) -> Path:
    """Return the FASTA used by the configured custom ABRicate database."""
    datadir = config.database_path("abricate_datadir")
    database_name = str(config.value("tools", "abricate", "database_name"))
    return datadir / database_name / "sequences"


def minimap2_command(
    reads: Sequence[Path], reference: Path, config: PipelineConfig
) -> list[str]:
    """Build a short-read PAF mapping command with explicit argument boundaries."""
    tool = config.value("tools", "reads_mapper")
    return [
        str(tool["executable"]),
        *[str(item) for item in tool.get("prefix_options", [])],
        *[str(item) for item in tool.get("options", [])],
        "-t",
        str(config.threads),
        str(reference),
        *[str(path) for path in reads],
    ]


def run_minimap2(
    reads: Sequence[Path],
    raw_path: Path,
    config: PipelineConfig,
    runner: CommandRunner,
) -> Path:
    """Run minimap2 and stream PAF records to the raw output directory."""
    runner.run(
        minimap2_command(reads, reference_sequences(config), config),
        tool="minimap2",
        log_path=raw_path.parent.parent / "logs" / "minimap2.log",
        stdout_path=raw_path,
    )
    return raw_path


def _integer(value: str, label: str, line_number: int) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ParseError(
            f"minimap2 PAF line {line_number} has invalid {label}: {value}"
        ) from exc


def _covered_bases(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    total = 0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start > current_end:
            total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    return total + current_end - current_start


def _target_fields(target: str) -> dict[str, str]:
    parts = target.split("~~~")
    return {
        "gene": parts[1] if len(parts) > 1 else target,
        "accession": parts[2] if len(parts) > 2 else target,
        "resistance": parts[3] if len(parts) > 3 else "",
    }


def parse_paf(path: Path, config: PipelineConfig) -> list[dict[str, Any]]:
    """Aggregate passing read alignments by reference gene.

    Coordinates and strand are deliberately left empty because those output fields
    describe an assembled contig feature, which direct reads do not provide.
    """
    tool = config.value("tools", "reads_mapper")
    min_identity = float(tool["min_identity"])
    min_coverage = float(tool["min_coverage"])
    min_mapq = int(tool.get("min_mapq", 0))
    min_length = int(tool.get("min_alignment_length", 1))
    min_support = int(tool.get("min_supporting_reads", 1))
    grouped: dict[str, dict[str, Any]] = {}
    try:
        handle = path.open("r", encoding="utf-8-sig")
    except OSError as exc:
        raise ParseError(f"Cannot read minimap2 PAF output: {path}") from exc
    with handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\r\n").split("\t")
            if len(fields) < 12:
                raise ParseError(
                    f"minimap2 PAF line {line_number} has fewer than 12 columns."
                )
            target = fields[5]
            target_length = _integer(fields[6], "target length", line_number)
            target_start = _integer(fields[7], "target start", line_number)
            target_end = _integer(fields[8], "target end", line_number)
            matches = _integer(fields[9], "matching bases", line_number)
            block_length = _integer(fields[10], "alignment block length", line_number)
            mapq = _integer(fields[11], "mapping quality", line_number)
            if (
                target_length <= 0
                or block_length <= 0
                or target_start < 0
                or target_end > target_length
                or target_start >= target_end
            ):
                raise ParseError(f"minimap2 PAF line {line_number} has invalid coordinates.")
            identity = 100.0 * matches / block_length
            if identity < min_identity or mapq < min_mapq or block_length < min_length:
                continue
            item = grouped.setdefault(
                target,
                {
                    "target_length": target_length,
                    "intervals": [],
                    "matches": 0,
                    "aligned_bases": 0,
                    "supporting_reads": 0,
                },
            )
            if item["target_length"] != target_length:
                raise ParseError(
                    f"minimap2 PAF target length changed for reference: {target}"
                )
            item["intervals"].append((target_start, target_end))
            item["matches"] += matches
            item["aligned_bases"] += block_length
            item["supporting_reads"] += 1
    rows: list[dict[str, Any]] = []
    for target, item in grouped.items():
        covered = _covered_bases(item["intervals"])
        pct_coverage = 100.0 * covered / item["target_length"]
        if pct_coverage < min_coverage or item["supporting_reads"] < min_support:
            continue
        row: dict[str, Any] = {
            "contig": "",
            "start": "",
            "end": "",
            "strand": "",
            "pct_identity": round(100.0 * item["matches"] / item["aligned_bases"], 3),
            "pct_coverage": round(pct_coverage, 3),
            "coverage": f"{covered}/{item['target_length']}",
            "gaps": "",
            "supporting_reads": item["supporting_reads"],
            "depth": round(item["aligned_bases"] / item["target_length"], 3),
        }
        row.update(_target_fields(target))
        rows.append(row)
    return sorted(rows, key=lambda row: (str(row["gene"]), str(row["accession"])))
