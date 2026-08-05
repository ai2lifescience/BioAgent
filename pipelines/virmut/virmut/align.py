"""Alignment stage."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_minimap2(
    query: Path,
    reference: Path,
    output_paf: Path,
    preset: str = "asm20",
) -> None:
    output_paf = Path(output_paf)
    output_paf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "minimap2",
        "-x",
        preset,
        "-c",
        "--cs",
        str(reference),
        str(query),
    ]
    with output_paf.open("w", encoding="utf-8") as out:
        subprocess.run(cmd, stdout=out, check=True)
