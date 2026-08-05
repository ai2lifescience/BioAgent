"""Read-only VFDB custom ABRicate database preflight."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .errors import DatabaseConfigurationError


def validate_database(config: PipelineConfig) -> dict[str, Any]:
    """Validate database directory, sequences, BLAST indexes, and metadata."""
    datadir = config.database_path("abricate_datadir")
    metadata = config.database_path("metadata")
    database_name = str(config.value("tools", "abricate", "database_name"))
    database_dir = datadir / database_name
    sequences = database_dir / "sequences"
    for path, label, directory in (
        (datadir, "ABRicate datadir", True),
        (database_dir, f"ABRicate database '{database_name}'", True),
        (sequences, "ABRicate sequences", False),
        (metadata, "VFDB metadata", False),
    ):
        valid = path.is_dir() if directory else path.is_file()
        if not valid:
            raise DatabaseConfigurationError(f"{label} does not exist: {path}")
        if not directory and (path.stat().st_size == 0 or not os.access(path, os.R_OK)):
            raise DatabaseConfigurationError(f"{label} is empty or unreadable: {path}")
    indexes = sorted(
        item.name
        for item in database_dir.iterdir()
        if item.is_file() and item.suffix.lower() in {".nhr", ".nin", ".nsq", ".ndb", ".not", ".ntf", ".nto"}
    )
    if not indexes:
        raise DatabaseConfigurationError(
            f"BLAST nucleotide database indexes are missing in: {database_dir}"
        )
    return {
        "name": database_name,
        "directory": str(database_dir),
        "sequences": sequences.name,
        "blast_indexes": indexes,
    }
