"""Command-line interface for the FASTQ-only bacterial pipeline."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Optional, Sequence

from .filtering import filter_snps
from .matrix import build_snp_matrix
from .reference import load_reference, resolve_reference
from .reporting import write_variants_table
from .snippy_pipeline import run_fastq_pipeline
from .tree import run_iqtree


LOGGER = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_taxid(value: str) -> str:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError("taxonid must be a positive integer")
    return value


def fraction(value: str) -> float:
    parsed = float(value)
    if not 0 < parsed <= 1:
        raise argparse.ArgumentTypeError("must be greater than 0 and at most 1")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bactmut-fastq",
        description=(
            "Call bacterial variants from FASTQ reads with Snippy, filter SNPs, "
            "and build an IQ-TREE phylogeny."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, help="directory containing FASTQ reads")
    parser.add_argument("--output", required=True, help="directory for pipeline outputs")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--reference", help="local reference FASTA")
    source_group.add_argument("--species", help="species name resolved from the GTDB database")
    source_group.add_argument(
        "--taxonid",
        type=positive_taxid,
        help="NCBI strain or species Taxonomy ID resolved from GTDB metadata",
    )
    parser.add_argument(
        "--threads",
        type=positive_int,
        default=max(1, min(8, os.cpu_count() or 1)),
        help="CPUs passed to each Snippy run and IQ-TREE",
    )
    parser.add_argument(
        "--min-coverage",
        type=fraction,
        default=0.9,
        help="minimum sample fraction callable at an SNP position",
    )
    parser.add_argument(
        "--window-size",
        type=positive_int,
        default=50,
        help="recombination scan window size in bp",
    )
    parser.add_argument(
        "--step-size",
        type=positive_int,
        default=10,
        help="recombination scan step size in bp",
    )
    parser.add_argument(
        "--sd-threshold",
        type=nonnegative_float,
        default=3.0,
        help="standard deviations above mean SNP density used to flag windows",
    )
    parser.add_argument("--verbose", action="store_true", help="enable detailed logging")
    return parser


def configure_logging(output_dir: Path, verbose: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(output_dir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[console, file_handler], force=True)


def run_pipeline(arguments: Mapping[str, object]) -> int:
    output_dir = Path(str(arguments["output"])).resolve()
    reference_path, temporary = resolve_reference(
        reference=_optional_text(arguments.get("reference")),
        species=_optional_text(arguments.get("species")),
        taxonid=_optional_text(arguments.get("taxonid")),
    )
    temporary_map = (
        reference_path.with_suffix(".contig_map.tsv") if temporary else None
    )
    if temporary_map and temporary_map.is_file():
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temporary_map, output_dir / "reference_contig_map.tsv")
    try:
        reference = load_reference(reference_path)
        samples = run_fastq_pipeline(
            reference=reference,
            fastq_dir=Path(str(arguments["input"])).resolve(),
            output_dir=output_dir,
            threads=int(arguments["threads"]),
        )
        result = filter_snps(
            samples=samples,
            reference_length=reference.length,
            min_coverage_fraction=float(arguments["min_coverage"]),
            window_size=int(arguments["window_size"]),
            step_size=int(arguments["step_size"]),
            sd_threshold=float(arguments["sd_threshold"]),
        )
        matrix_path = output_dir / "matrix.tsv"
        build_snp_matrix(samples, reference, result.final_positions, matrix_path)
        write_variants_table(
            output_dir / "variants.tsv",
            reference,
            samples,
            result,
            output_dir / "variants_summary.txt",
        )
        tree_status, _ = run_iqtree(
            matrix_path,
            output_dir / "tree",
            threads=int(arguments["threads"]),
        )
        LOGGER.info(
            "Completed: %d initial SNPs, %d final SNPs; tree %s",
            len(result.initial_positions),
            len(result.final_positions),
            tree_status,
        )
        return 0
    finally:
        if temporary:
            try:
                reference_path.unlink(missing_ok=True)
                if temporary_map:
                    temporary_map.unlink(missing_ok=True)
            except OSError as error:
                LOGGER.warning("Unable to remove temporary reference %s: %s", reference_path, error)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output).resolve()
    configure_logging(output_dir, args.verbose)
    try:
        return run_pipeline(vars(args))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        LOGGER.error("Pipeline failed: %s", error)
        return 2


def _optional_text(value: object) -> Optional[str]:
    return None if value is None else str(value)
