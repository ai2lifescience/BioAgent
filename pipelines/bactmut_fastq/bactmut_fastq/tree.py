"""IQ-TREE integration for tabular SNP matrices."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


LOGGER = logging.getLogger(__name__)


def run_iqtree(
    matrix_tsv: Path,
    output_prefix: Path,
    model: str = "GTR+G",
    threads: int = 1,
) -> Tuple[str, Optional[Path]]:
    if type(threads) is not int or threads < 1:
        raise ValueError("IQ-TREE threads must be an integer >= 1")

    with Path(matrix_tsv).open("r", encoding="utf-8") as matrix_file:
        header = next(matrix_file).rstrip("\n").split("\t")
        samples = header[1:]
        rows = [
            (int(fields[0]), fields[1:])
            for line in matrix_file
            if line.strip()
            for fields in [line.rstrip("\n").split("\t")]
        ]
    if not rows:
        message = "skipped: no SNPs remained after filtering"
        LOGGER.warning(message)
        return message, None

    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    alignment_fasta = output_prefix.with_suffix(".fasta")
    rows.sort(key=lambda row: row[0])
    with alignment_fasta.open("w", encoding="ascii", newline="\n") as handle:
        for index, sample in enumerate(samples):
            sequence = "".join(values[index] for _, values in rows)
            handle.write(f">{sample}\n{sequence}\n")

    executable = shutil.which("iqtree2") or shutil.which("iqtree")
    if executable is None:
        message = "not built: IQ-TREE (iqtree2 or iqtree) was not found on PATH"
        LOGGER.warning(message)
        return message, None
    command = [
        executable,
        "-s",
        str(alignment_fasta),
        "-st",
        "DNA",
        "-m",
        model,
        "-nt",
        str(threads),
        "-pre",
        str(output_prefix),
        "-redo",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().replace("\n", " ")
        message = f"failed: IQ-TREE exited with code {completed.returncode}: {detail}"
        LOGGER.error(message)
        return message, None

    treefile = Path(f"{output_prefix}.treefile")
    if not treefile.is_file():
        message = "failed: IQ-TREE returned success but did not create a .treefile"
        LOGGER.error(message)
        return message, None
    final_tree = output_prefix.parent / "final_tree.nwk"
    shutil.copyfile(treefile, final_tree)
    return "completed", final_tree
