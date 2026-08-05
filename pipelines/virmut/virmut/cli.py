"""Command-line parsing for virmut."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence


def positive_taxid(value: str) -> str:
    """Return a taxon id only when it is a positive integer string."""
    if not value.isdigit() or int(value) <= 0:
        raise argparse.ArgumentTypeError("taxonid must be a positive integer")
    return value


def positive_int(value: str) -> int:
    """Return a positive integer for CLI options."""
    if not value.isdigit() or int(value) <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return int(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="virmut")
    parser.add_argument(
        "--input",
        required=True,
        help="input FASTA file/directory in fasta mode, or FASTQ directory in fastq mode",
    )
    parser.add_argument("--output", required=True, help="output directory")
    parser.add_argument(
        "--mode",
        choices=("fasta", "fastq"),
        default="fasta",
        help="input mode: assembled FASTA genomes or raw FASTQ reads",
    )
    parser.add_argument(
        "--threads",
        type=positive_int,
        default=1,
        help="threads for FASTQ alignment and sorting steps",
    )
    parser.add_argument("--annotate", action="store_true", default=True)

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--reference", help="local reference FASTA")
    source_group.add_argument("--species", help="species name resolved from local SEQ_DB")
    source_group.add_argument(
        "--taxonid",
        type=positive_taxid,
        help="positive integer taxon id resolved from local SEQ_DB",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from pathlib import Path

    from virmut.align import run_minimap2
    from virmut.ivar_variants import run_fastq_pipeline
    from virmut.matrix import build_snp_matrix
    from virmut.reference import resolve_reference
    from virmut.snp import build_variants_table, call_snps
    from virmut.tree import run_iqtree
    from virmut.utils import collect_input_fastas, ensure_single_record

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.reference:
        ensure_single_record(Path(args.reference))
    resolved = resolve_reference(
        reference=args.reference,
        species=args.species,
        taxonid=args.taxonid,
        db_fasta=os.environ.get("VIRUS_DB"),
        db_metadata=os.environ.get("VIRUS_METADATA"),
    )
    output_dir = Path(args.output) if args.output else Path("results")

    pafs = {}
    ivar_variants = None
    if args.mode == "fastq":
        snp_tsvs, ivar_variants = run_fastq_pipeline(
            reference=resolved.path,
            fastq_dir=Path(args.input),
            output_dir=output_dir,
            threads=args.threads,
        )
    else:
        input_fastas = collect_input_fastas(Path(args.input))
        for input_fasta in input_fastas.values():
            ensure_single_record(input_fasta)

        snp_tsvs = {}
        for sample, input_fasta in input_fastas.items():
            output_paf = output_dir / "align" / f"{sample}.paf"
            run_minimap2(
                query=input_fasta,
                reference=resolved.path,
                output_paf=output_paf,
            )
            output_tsv = output_dir / "snps" / f"{sample}.tsv"
            call_snps(
                paf=output_paf,
                reference=resolved.path,
                output_tsv=output_tsv,
            )
            pafs[sample] = output_paf
            snp_tsvs[sample] = output_tsv
    output_matrix = output_dir / "matrix.tsv"
    build_snp_matrix(
        snp_tsvs=snp_tsvs,
        output_tsv=output_matrix,
    )
    if args.annotate:
        build_variants_table(
            pafs=pafs,
            reference=resolved.path,
            output_tsv=output_dir / "variants.tsv",
            output_summary=output_dir / "variants_summary.txt",
            ivar_variants=ivar_variants,
        )
    output_tree = output_dir / "tree"
    run_iqtree(
        matrix_tsv=output_matrix,
        output_prefix=output_tree,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
