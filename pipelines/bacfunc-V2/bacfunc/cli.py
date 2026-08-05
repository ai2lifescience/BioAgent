"""BacFunc general and Agent-specific command-line entry points."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .batch import run_samples
from .doctor import run_doctor
from .input import discover_samples


def _run_arguments(parser: argparse.ArgumentParser) -> None:
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--input", nargs="+", type=Path)
    sources.add_argument("--input-dir", type=Path)
    parser.add_argument("--input-type", choices=("auto", "reads", "genome"), default="auto")
    parser.add_argument(
        "--analysis-mode",
        choices=("auto", "reads", "genome", "assemble"),
        default="auto",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-id")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threads", type=int, default=8)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bacfunc",
        description="Gene-level eggNOG-mapper annotation for metagenomes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    _run_arguments(run_parser)
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config", type=Path)
    doctor_parser.add_argument("--output", type=Path)
    doctor_parser.add_argument("--json", action="store_true", dest="as_json")
    subparsers.add_parser("version")
    return parser


def _execute_run(namespace: argparse.Namespace) -> int:
    try:
        samples = discover_samples(
            namespace.input or [],
            namespace.output,
            input_directory=namespace.input_dir,
            sample_id=namespace.sample_id,
            input_type=namespace.input_type,
            analysis_mode=namespace.analysis_mode,
        )
        run_samples(
            samples,
            namespace.output,
            config_path=namespace.config,
            dry_run=namespace.dry_run,
            threads=namespace.threads,
        )
        return 0
    except Exception as exc:
        print(f"bacfunc: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    if namespace.command == "version":
        print(__version__)
        return 0
    if namespace.command == "doctor":
        report = run_doctor(namespace.config, namespace.output)
        if namespace.as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for item in report["checks"]:
                print(f"[{item['level'].upper()}] {item['name']}: {item['message']}")
            print("READY" if report["ok"] else "NOT READY")
        return 0 if report["ok"] else 1
    return _execute_run(namespace)


def fasta_main(argv: Sequence[str] | None = None) -> int:
    """FASTA-only Agent entry point."""
    parser = argparse.ArgumentParser(prog="bacfunc-fasta")
    parser.add_argument("--assembly", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-id")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threads", type=int, default=8)
    namespace = parser.parse_args(argv)
    namespace.input = [namespace.assembly]
    namespace.input_dir = None
    namespace.input_type = "genome"
    namespace.analysis_mode = "genome"
    return _execute_run(namespace)


def fastq_main(argv: Sequence[str] | None = None) -> int:
    """FASTQ-only Agent entry point with explicit R1/R2 roles."""
    parser = argparse.ArgumentParser(prog="bacfunc-fastq")
    parser.add_argument("--read1", required=True, type=Path)
    parser.add_argument("--read2", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-id")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analysis-mode", choices=("assemble", "reads"), default="assemble")
    parser.add_argument("--threads", type=int, default=8)
    namespace = parser.parse_args(argv)
    namespace.input = [namespace.read1] + ([namespace.read2] if namespace.read2 else [])
    namespace.input_dir = None
    namespace.input_type = "reads"
    return _execute_run(namespace)

