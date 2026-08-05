"""Command-line interface for bactmut-fasta."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from .pipeline import run_pipeline


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_int_string(value: str) -> str:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
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
        prog="bactmut-fasta",
        description=(
            "Compare bacterial genomes to a FASTA reference, detect and filter SNPs, "
            "write an SNP alignment, and optionally build an IQ-TREE phylogeny."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    reference_group = parser.add_mutually_exclusive_group()
    reference_group.add_argument(
        "--reference",
        help="reference genome FASTA path",
    )
    reference_group.add_argument(
        "--species",
        help="species name (e.g., 'Escherichia coli') to automatically fetch reference genome",
    )
    reference_group.add_argument(
        "--taxonid",
        type=positive_int_string,
        help=(
            "NCBI Taxonomy ID (strain-level ncbi_taxid or species-level "
            "ncbi_species_taxid) to select GTDB representative reference"
        ),
    )
    parser.add_argument(
        "--query_dir",
        help="directory containing at least five query genome FASTA files; required unless --simulate is used",
    )
    parser.add_argument("--out_dir", required=True, help="directory for all pipeline outputs")
    parser.add_argument(
        "--window_size", type=positive_int, default=50, help="recombination scan window size in bp"
    )
    parser.add_argument(
        "--step_size", type=positive_int, default=10, help="recombination scan step size in bp"
    )
    parser.add_argument(
        "--sd_threshold",
        type=nonnegative_float,
        default=3.0,
        help="number of standard deviations above mean SNP density used to flag windows",
    )
    parser.add_argument(
        "--min_coverage",
        type=fraction,
        default=0.9,
        help="minimum fraction of strains that must cover an SNP position",
    )
    parser.add_argument(
        "--aligner",
        choices=("auto", "minimap2", "internal"),
        default="auto",
        help="alignment backend; internal supports equal-length full genomes only",
    )
    parser.add_argument(
        "--threads",
        type=positive_int,
        default=max(1, min(8, os.cpu_count() or 1)),
        help="total alignment worker/thread budget",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help=(
            "generate query genomes with known SNPs and validate recovery; "
            "requires --reference, --species, or --taxonid"
        ),
    )
    parser.add_argument(
        "--simulate_snp_rate",
        type=fraction,
        default=0.001,
        help="per-genome SNP fraction in simulation mode",
    )
    parser.add_argument(
        "--simulate_samples",
        type=positive_int,
        default=5,
        help="number of genomes generated in simulation mode (minimum 5)",
    )
    parser.add_argument("--seed", type=int, default=42, help="simulation random seed")
    parser.add_argument("--verbose", action="store_true", help="enable detailed progress logging")
    return parser


def configure_logging(out_dir: Path, verbose: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(out_dir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[console, file_handler], force=True)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not (args.reference or args.species or args.taxonid):
        parser.error("--reference, --species, or --taxonid is required, including with --simulate")
    if not args.simulate and not args.query_dir:
        parser.error("--query_dir is required unless --simulate is enabled")
    if args.simulate_samples < 5:
        parser.error("--simulate_samples must be at least 5")
    out_dir = Path(args.out_dir).resolve()
    configure_logging(out_dir, args.verbose)
    try:
        exit_code = run_pipeline(vars(args))
    except (OSError, ValueError, RuntimeError) as error:
        logging.getLogger(__name__).error("Pipeline failed: %s", error)
        raise SystemExit(2) from error
    raise SystemExit(exit_code)
