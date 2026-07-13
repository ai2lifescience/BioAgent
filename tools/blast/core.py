"""BLAST tool implementations."""

from __future__ import annotations

from typing import Any

from bio_data.blast import run_blast_search as _run_blast_search


def run_blast_search(
    sequence: str | None = None,
    rid: str | None = None,
    program: str = "blastn",
    database: str = "nt",
    hitlist_size: int = 10,
    expect: float = 10.0,
    wait: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    return _run_blast_search(
        sequence=sequence,
        rid=rid,
        program=program,
        database=database,
        hitlist_size=hitlist_size,
        expect=expect,
        wait=wait,
        timeout_seconds=timeout_seconds,
    )
