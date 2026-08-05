"""Prepare a custom ABRicate database from official MEGARes files."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Mapping, Sequence

from bacarg.command import CommandRunner
from bacarg.manifest import sha256_file, utc_now
from bacarg.metadata import OUTPUT_FIELDS, load_metadata, normalize_accession
from bacarg.outputs import write_json, write_tsv
from bacarg.qc import iter_fasta


def _safe_header(value: str) -> str:
    return value.replace("~~~", "_").replace("\t", " ").strip()


def prepare_database(
    fasta: Path,
    metadata_path: Path,
    datadir: Path,
    *,
    database_name: str = "megares_v3",
    field_mapping: Mapping[str, str] | None = None,
    makeblastdb: str = "makeblastdb",
    makeblastdb_prefix_options: Sequence[str] = (),
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Create sequences, normalized metadata, BLAST indexes, and manifest."""
    target = datadir.expanduser().resolve() / database_name
    if target.exists() and not force:
        raise FileExistsError(f"Database already exists; use --force to replace it: {target}")
    command = [
        makeblastdb,
        *[str(item) for item in makeblastdb_prefix_options],
        "-in", str(target / "sequences"),
        "-dbtype", "nucl",
        "-out", str(target / "sequences"),
        "-title", database_name,
    ]
    if dry_run:
        return command
    metadata = load_metadata(metadata_path, field_mapping)
    records = list(iter_fasta(fasta))
    if not records:
        raise ValueError("MEGARes nucleotide FASTA contains no records.")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    sequence_path = target / "sequences"
    normalized_rows: list[dict[str, str]] = []
    with sequence_path.open("w", encoding="utf-8", newline="\n") as handle:
        for identifier, sequence in records:
            accession = normalize_accession(identifier)
            row = metadata.get(accession)
            if row is None:
                raise ValueError(f"FASTA accession is absent from MEGARes metadata: {identifier}")
            gene = _safe_header(row.get("gene") or identifier)
            resistance = _safe_header(row.get("resistance") or row.get("class") or "unknown")
            handle.write(
                f">{database_name}~~~{gene}~~~{identifier}~~~{resistance} "
                f"{_safe_header(row.get('product', ''))}\n{sequence}\n"
            )
            normalized_rows.append({field: row.get(field, "") for field in OUTPUT_FIELDS})
    write_tsv(target / "metadata.normalized.tsv", normalized_rows, OUTPUT_FIELDS)
    runner = CommandRunner()
    runner.run(
        command,
        tool="makeblastdb",
        log_path=target / "makeblastdb.log",
    )
    write_json(
        target / "database_manifest.json",
        {
            "schema_version": "1.0",
            "database_name": database_name,
            "database_version": "3.0",
            "created_at_utc": utc_now(),
            "source_fasta": {"name": fasta.name, "sha256": sha256_file(fasta)},
            "source_metadata": {
                "name": metadata_path.name,
                "sha256": sha256_file(metadata_path),
            },
            "record_count": len(records),
            "commands": runner.commands,
        },
    )
    return command


def _field_map(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise argparse.ArgumentTypeError("Field mappings must use LOGICAL=SOURCE.")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fasta", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--datadir", required=True, type=Path)
    parser.add_argument("--database-name", default="megares_v3")
    parser.add_argument("--field-map", action="append", default=[])
    parser.add_argument("--makeblastdb", default="makeblastdb")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    command = prepare_database(
        args.fasta,
        args.metadata,
        args.datadir,
        database_name=args.database_name,
        field_mapping=_field_map(args.field_map),
        makeblastdb=args.makeblastdb,
        force=args.force,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
