"""Direct translated-search functional annotation for quality-controlled reads."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .command import CommandRunner
from .config import PipelineConfig
from .errors import ExternalToolError, ParseError
from .input import open_sequence_text


DIAMOND_COLUMNS = (
    "qseqid", "sseqid", "pident", "length", "qlen", "slen", "evalue", "bitscore"
)
READ_ANNOTATION_FIELDS = (
    "accession", "supporting_reads", "mean_pct_identity",
    "mean_query_coverage", "mean_bitscore",
)


def fastq_to_fasta(reads: Sequence[Path], target: Path) -> Path:
    """Convert trimmed FASTQ files to one FASTA with collision-free query IDs."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as output:
        for file_index, path in enumerate(reads, start=1):
            with open_sequence_text(path) as handle:
                record: list[str] = []
                record_number = 0
                for raw in handle:
                    record.append(raw.rstrip("\r\n"))
                    if len(record) != 4:
                        continue
                    header, sequence, plus, quality = record
                    if (
                        not header.startswith("@")
                        or not plus.startswith("+")
                        or not sequence
                        or len(sequence) != len(quality)
                    ):
                        raise ParseError(f"Malformed trimmed FASTQ record in {path}")
                    record_number += 1
                    original = re.sub(r"[^A-Za-z0-9_.:-]+", "_", header[1:].split()[0])
                    query = f"R{file_index}_{record_number}_{original or 'read'}"
                    output.write(f">{query}\n{sequence}\n")
                    record = []
                if record:
                    raise ParseError(f"Incomplete trimmed FASTQ record in {path}")
    return target


def diamond_command(query: Path, output: Path, config: PipelineConfig) -> list[str]:
    """Build DIAMOND blastx against the deployed eggNOG protein database."""
    tool = config.value("tools", "reads_search")
    database = config.eggnog_path("data_dir") / "eggnog_proteins.dmnd"
    return [
        str(tool["executable"]),
        *[str(item) for item in tool.get("prefix_options", [])],
        "blastx",
        "--db", str(database),
        "--query", str(query),
        "--out", str(output),
        "--outfmt", "6", *DIAMOND_COLUMNS,
        "--max-target-seqs", "1",
        "--threads", str(config.threads),
        "--evalue", str(tool["evalue"]),
        "--id", str(tool["min_identity"]),
        "--query-cover", str(tool["min_query_coverage"]),
        *[str(item) for item in tool.get("options", [])],
    ]


def run_diamond(
    query: Path, output: Path, config: PipelineConfig, runner: CommandRunner
) -> Path:
    """Run the translated search and require its output file to exist."""
    runner.run(
        diamond_command(query, output, config),
        tool="DIAMOND blastx",
        log_path=output.parent.parent / "logs" / "diamond.log",
    )
    if not runner.dry_run and not output.is_file():
        raise ExternalToolError(f"DIAMOND completed without its result file: {output}")
    return output


def parse_diamond(path: Path) -> dict[str, dict[str, Any]]:
    """Parse the best hit for each uniquely named read and validate every field."""
    hits: dict[str, dict[str, Any]] = {}
    try:
        handle = path.open("r", encoding="utf-8-sig")
    except OSError as exc:
        raise ParseError(f"Cannot read DIAMOND output: {path}") from exc
    with handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\r\n").split("\t")
            if len(fields) != len(DIAMOND_COLUMNS):
                raise ParseError(
                    f"DIAMOND line {line_number} has {len(fields)} columns; "
                    f"expected {len(DIAMOND_COLUMNS)}."
                )
            row = dict(zip(DIAMOND_COLUMNS, fields))
            try:
                length = int(row["length"])
                query_length = int(row["qlen"])
                identity = float(row["pident"])
                evalue = float(row["evalue"])
                bitscore = float(row["bitscore"])
            except ValueError as exc:
                raise ParseError(f"DIAMOND line {line_number} has invalid numeric data.") from exc
            if length <= 0 or query_length <= 0:
                raise ParseError(f"DIAMOND line {line_number} has invalid sequence lengths.")
            hits[row["qseqid"]] = {
                "subject": row["sseqid"],
                "identity": identity,
                "query_coverage": min(100.0, 100.0 * length * 3 / query_length),
                "evalue": evalue,
                "bitscore": bitscore,
            }
    return hits


def write_seed_orthologs(
    path: Path, hits: Mapping[str, Mapping[str, Any]]
) -> Path:
    """Write eggNOG-mapper's required four-column seed-ortholog table."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for query in sorted(hits):
            hit = hits[query]
            handle.write(
                f"{query}\t{hit['subject']}\t{hit['evalue']}\t{hit['bitscore']}\n"
            )
    return path


def annotation_command(
    seed_table: Path, output_dir: Path, prefix: str, config: PipelineConfig
) -> list[str]:
    """Build eggNOG-mapper's documented no-search annotation command."""
    tool = config.value("tools", "eggnog")
    return [
        str(tool["executable"]),
        *[str(item) for item in tool.get("prefix_options", [])],
        "-m", "no_search",
        "--annotate_hits_table", str(seed_table),
        "--data_dir", str(config.eggnog_path("data_dir")),
        "--cpu", str(config.threads),
        "--output", prefix,
        "--output_dir", str(output_dir),
        "--override",
    ]


def run_annotation(
    seed_table: Path,
    output_dir: Path,
    prefix: str,
    config: PipelineConfig,
    runner: CommandRunner,
) -> Path:
    """Annotate DIAMOND seed orthologs with the deployed eggNOG metadata."""
    runner.run(
        annotation_command(seed_table, output_dir, prefix, config),
        tool="eggNOG-mapper annotation",
        log_path=output_dir.parent / "logs" / "eggnog_reads.log",
    )
    annotations = output_dir / f"{prefix}.emapper.annotations"
    if not runner.dry_run and (not annotations.is_file() or annotations.stat().st_size == 0):
        raise ExternalToolError(
            f"eggNOG-mapper completed without annotations: {annotations}"
        )
    return annotations


def aggregate_annotations(
    header: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    hits: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Aggregate read annotations by real eggNOG seed-ortholog accession."""
    grouped: dict[str, dict[str, Any]] = {}
    for source in rows:
        read_id = str(source.get("query", ""))
        hit = hits.get(read_id, {})
        accession = str(source.get("seed_ortholog", "") or hit.get("subject", ""))
        if not accession:
            raise ParseError(f"eggNOG read annotation has no seed ortholog: {read_id}")
        item = grouped.setdefault(
            accession,
            {
                "row": {field: str(source.get(field, "")) for field in header},
                "reads": set(),
                "identities": [],
                "coverages": [],
                "bitscores": [],
            },
        )
        for field in header:
            if not item["row"].get(field) and source.get(field):
                item["row"][field] = str(source[field])
        item["reads"].add(read_id)
        if hit:
            item["identities"].append(float(hit["identity"]))
            item["coverages"].append(float(hit["query_coverage"]))
            item["bitscores"].append(float(hit["bitscore"]))
    output: list[dict[str, Any]] = []
    for accession, item in sorted(grouped.items()):
        row = item["row"]
        row["query"] = accession
        row["accession"] = accession
        row["supporting_reads"] = len(item["reads"])
        row["mean_pct_identity"] = (
            round(sum(item["identities"]) / len(item["identities"]), 3)
            if item["identities"] else ""
        )
        row["mean_query_coverage"] = (
            round(sum(item["coverages"]) / len(item["coverages"]), 3)
            if item["coverages"] else ""
        )
        row["mean_bitscore"] = (
            round(sum(item["bitscores"]) / len(item["bitscores"]), 3)
            if item["bitscores"] else ""
        )
        output.append(row)
    output_header = list(header)
    for field in READ_ANNOTATION_FIELDS:
        if field not in output_header:
            output_header.append(field)
    return output_header, output
