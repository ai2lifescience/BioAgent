"""IQ-TREE integration."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


LOGGER = logging.getLogger(__name__)


def build_tree(
    matrix_path: Path, output_dir: Path, snp_count: int, threads: int = 1
) -> Tuple[str, Optional[Path]]:
    if type(threads) is not int or threads < 1:
        raise ValueError("IQ-TREE threads must be an integer >= 1")
    thread_count = threads
    if snp_count == 0:
        message = "skipped: no SNPs remained after filtering"
        LOGGER.warning(message)
        return message, None
    executable = shutil.which("iqtree2") or shutil.which("iqtree")
    if executable is None:
        message = "not built: IQ-TREE (iqtree2 or iqtree) was not found on PATH"
        LOGGER.warning("%s; the SNP matrix can be used to build the tree manually", message)
        return message, None
    prefix = output_dir / "iqtree_run"
    command = [
        executable,
        "-s",
        str(matrix_path),
        "-m",
        "MFP",
        "-bb",
        "1000",
        "-nt",
        str(thread_count),
        "-pre",
        str(prefix),
        "-redo",
    ]
    LOGGER.info("Running IQ-TREE")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().replace("\n", " ")
        message = f"failed: IQ-TREE exited with code {completed.returncode}: {detail}"
        LOGGER.error(message)
        return message, None
    treefile = Path(f"{prefix}.treefile")
    if not treefile.is_file():
        message = "failed: IQ-TREE returned success but did not create a .treefile"
        LOGGER.error(message)
        return message, None
    final_tree = output_dir / "final_tree.nwk"
    shutil.copyfile(treefile, final_tree)
    return "completed", final_tree

