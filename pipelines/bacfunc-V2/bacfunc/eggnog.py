"""eggNOG database validation, command construction, and dynamic parsing."""

from __future__ import annotations

import csv
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from .command import CommandRunner
from .config import PipelineConfig
from .errors import DatabaseConfigurationError, ParseError


REQUIRED_DATABASE_FILES = (
    "eggnog.db",
    "eggnog.taxa.db",
    "eggnog.taxa.db.traverse.pkl",
    "eggnog_proteins.dmnd",
)
TERM_COLUMNS = {
    "GOs": "GO",
    "COG_category": "COG_CATEGORY",
    "eggNOG_OGs": "EGGNOG_OG",
    "EC": "EC",
    "KEGG_ko": "KEGG_KO",
    "KEGG_Pathway": "KEGG_PATHWAY",
    "KEGG_Module": "KEGG_MODULE",
    "KEGG_Reaction": "KEGG_REACTION",
    "KEGG_rclass": "KEGG_RCLASS",
    "BRITE": "BRITE",
    "KEGG_TC": "KEGG_TC",
    "CAZy": "CAZY",
    "BiGG_Reaction": "BIGG_REACTION",
    "PFAMs": "PFAM",
}
TERM_FIELDS = ["sample_id", "gene_id", "namespace", "term_id", "term_name", "source_column"]


def validate_database_path(data_dir: Path) -> dict[str, Any]:
    """Read-only eggNOG v5 preflight including SQLite validation."""
    data_dir = data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise DatabaseConfigurationError(f"eggNOG data directory does not exist: {data_dir}")
    files: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_DATABASE_FILES:
        path = data_dir / name
        if not path.is_file():
            raise DatabaseConfigurationError(f"Required eggNOG database file is missing: {path}")
        if path.stat().st_size == 0 or not os.access(path, os.R_OK):
            raise DatabaseConfigurationError(f"eggNOG database file is empty or unreadable: {path}")
        stat = path.stat()
        files[name] = {
            "size": stat.st_size,
            "modified_time": stat.st_mtime,
        }
    database = data_dir / "eggnog.db"
    detected_version = "unknown"
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        try:
            connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for table in ("version", "metadata", "eggnog_version"):
                if table not in tables:
                    continue
                columns = [
                    str(row[1])
                    for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                ]
                version_column = next(
                    (item for item in columns if "version" in item.lower()), None
                )
                if version_column:
                    row = connection.execute(
                        f'SELECT "{version_column}" FROM "{table}" LIMIT 1'
                    ).fetchone()
                    if row and row[0] not in (None, ""):
                        detected_version = str(row[0])
                        break
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise DatabaseConfigurationError(f"eggnog.db is not a valid readable SQLite database: {exc}") from exc
    return {
        "name": "eggNOG",
        "expected_major_version": "5",
        "detected_version": detected_version,
        "files": files,
    }


def eggnog_command(
    proteins: Path, output_dir: Path, prefix: str, config: PipelineConfig
) -> list[str]:
    """Build the pinned DIAMOND-mode eggNOG-mapper command."""
    tool = config.value("tools", "eggnog")
    return [
        str(tool["executable"]),
        *[str(item) for item in tool.get("prefix_options", [])],
        "-i", str(proteins),
        *[str(item) for item in tool.get("options", [])],
        "-m", str(tool["search_mode"]),
        "--data_dir", str(config.eggnog_path("data_dir")),
        "--cpu", str(config.threads),
        "--output", prefix,
        "--output_dir", str(output_dir),
    ]


def run_eggnog(
    proteins: Path,
    raw_dir: Path,
    sample_id: str,
    config: PipelineConfig,
    runner: CommandRunner,
    warnings: list[str],
) -> Path:
    """Run eggNOG-mapper and record optional-file availability."""
    runner.run(
        eggnog_command(proteins, raw_dir, sample_id, config),
        tool="eggNOG-mapper",
        log_path=raw_dir.parent / "logs" / "eggnog.log",
    )
    annotations = raw_dir / f"{sample_id}.emapper.annotations"
    if not runner.dry_run:
        if not annotations.is_file() or annotations.stat().st_size == 0:
            raise ParseError(f"eggNOG annotations are missing or empty: {annotations}")
        for suffix in ("seed_orthologs", "hits"):
            optional = raw_dir / f"{sample_id}.emapper.{suffix}"
            if not optional.is_file():
                warnings.append(
                    f"Optional eggNOG-mapper output was not generated: {optional.name}"
                )
    return annotations


def parse_annotations(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a dynamic ``#query`` header and preserve every source column."""
    header: list[str] | None = None
    data_lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for raw in handle:
                line = raw.rstrip("\r\n")
                if not line:
                    continue
                if line.startswith("##"):
                    continue
                if line.startswith("#"):
                    candidate = line[1:].split("\t")
                    if candidate and candidate[0].strip().lower() == "query":
                        header = [item.strip() for item in candidate]
                    continue
                data_lines.append(line)
    except OSError as exc:
        raise ParseError(f"Cannot read eggNOG annotations: {path}") from exc
    if header is None:
        raise ParseError(f"eggNOG annotations have no #query header: {path}")
    reader = csv.DictReader(data_lines, fieldnames=header, delimiter="\t")
    rows = [
        {field: str(row.get(field, "") or "") for field in header}
        for row in reader
    ]
    return header, rows


def _terms(value: str, namespace: str) -> Iterable[str]:
    value = value.strip()
    if not value or value == "-":
        return ()
    if namespace == "COG_CATEGORY":
        return tuple(char for char in value if char.isalnum())
    return tuple(
        item.strip()
        for item in re.split(r"[,;]", value)
        if item.strip() and item.strip() != "-"
    )


def expand_terms(
    rows: Iterable[Mapping[str, str]], sample_id: str
) -> list[dict[str, str]]:
    """Expand supported namespaces into a deterministic, deduplicated long table."""
    terms: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        gene_id = str(row.get("query", ""))
        for source, namespace in TERM_COLUMNS.items():
            for term in _terms(str(row.get(source, "")), namespace):
                key = (gene_id, namespace, term, source)
                terms[key] = {
                    "sample_id": sample_id,
                    "gene_id": gene_id,
                    "namespace": namespace,
                    "term_id": term,
                    "term_name": "",
                    "source_column": source,
                }
    return [
        terms[key]
        for key in sorted(terms, key=lambda item: (item[0], item[1], item[2], item[3]))
    ]
