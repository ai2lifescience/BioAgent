"""End-to-end BacFunc orchestration."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .assembly import prepare_assembly, prepare_reads
from .command import CommandRunner, render_commands
from .config import load_config
from .eggnog import TERM_FIELDS, expand_terms, parse_annotations, run_eggnog, validate_database_path
from .input import InputSet, validate_inputs
from .manifest import database_manifest, input_records, runtime_record, utc_now
from .outputs import write_json, write_tsv
from .prokka import run_prokka
from .qc import assembly_qc, count_fasta_records, fastq_qc
from .read_search import (
    READ_ANNOTATION_FIELDS, aggregate_annotations, fastq_to_fasta, parse_diamond,
    run_annotation, run_diamond, write_seed_orthologs,
)
from .versions import probe_version


def _write_status(
    output: Path,
    status: str,
    sample_id: str,
    input_type: str,
    analysis_mode: str,
    dry_run: bool,
    warnings: list[str],
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "status": status,
        "pipeline": "bacfunc",
        "pipeline_version": __version__,
        "sample_id": sample_id,
        "input_type": input_type,
        "analysis_mode": analysis_mode,
        "dry_run": dry_run,
        "warnings": warnings,
    }
    payload.update(extra)
    write_json(output / "status.json", payload)


def run_pipeline(
    inputs: Sequence[Path],
    output: Path,
    *,
    sample_id: str | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
    threads: int | None = None,
    input_type: str = "auto",
    analysis_mode: str = "auto",
) -> dict[str, Any]:
    """Run gene-level eggNOG annotation without aggregation or abundance."""
    output = Path(output).expanduser().resolve()
    validated: InputSet = validate_inputs(
        inputs,
        output,
        sample_id,
        input_type=input_type,
        analysis_mode=analysis_mode,
    )
    output.mkdir(parents=True, exist_ok=True)
    raw_dir, logs_dir, work_dir = output / "raw", output / "logs", output / "work"
    for directory in (raw_dir, logs_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    started = utc_now()
    pipeline_log = logs_dir / "pipeline.log"
    pipeline_log.write_text(f"START bacfunc {started}\n", encoding="utf-8")
    runner = CommandRunner(dry_run=dry_run)
    _write_status(
        output,
        "running",
        validated.sample_id,
        validated.input_type,
        validated.analysis_mode,
        dry_run,
        warnings,
    )
    try:
        config = load_config(config_path)
        if threads is not None:
            from dataclasses import replace
            config = replace(config, threads=threads)
        deployed_manifest = database_manifest(
            config.eggnog_path("manifest", required=False), warnings
        )
        if config.value("runtime", "strict_manifest", required=False) and deployed_manifest is None:
            raise RuntimeError("A database manifest is required by runtime.strict_manifest.")
        database_info: dict[str, Any] | None = None
        if not dry_run:
            database_info = validate_database_path(config.eggnog_path("data_dir"))
        assembly_source = "not_applicable"
        assembly_metrics: dict[str, Any] = {}
        protein_count: int | None = None
        reads_metrics: dict[str, Any] = {}
        if validated.analysis_mode == "reads":
            prepared = prepare_reads(validated, work_dir, config, runner)
            reads_fasta = work_dir / "reads" / "trimmed_reads.fasta"
            if not dry_run:
                fastq_to_fasta(prepared.trimmed_reads, reads_fasta)
            diamond_path = raw_dir / "reads_diamond.tsv"
            run_diamond(reads_fasta, diamond_path, config, runner)
            seed_path = raw_dir / "reads.emapper.seed_orthologs"
            if dry_run:
                annotations_path = run_annotation(
                    seed_path, raw_dir, validated.sample_id, config, runner
                )
                header = ["query", *READ_ANNOTATION_FIELDS]
                gene_rows: list[dict[str, Any]] = []
                term_rows: list[dict[str, str]] = []
            else:
                diamond_hits = parse_diamond(diamond_path)
                write_seed_orthologs(seed_path, diamond_hits)
                if diamond_hits:
                    annotations_path = run_annotation(
                        seed_path, raw_dir, validated.sample_id, config, runner
                    )
                    source_header, source_rows = parse_annotations(annotations_path)
                    header, gene_rows = aggregate_annotations(
                        source_header, source_rows, diamond_hits
                    )
                    if not gene_rows:
                        warnings.append("eggNOG annotations contain no read-level rows.")
                else:
                    header = ["query", *READ_ANNOTATION_FIELDS]
                    gene_rows = []
                    warnings.append("DIAMOND found no reads passing the configured thresholds.")
                term_rows = expand_terms(gene_rows, validated.sample_id)
                raw_read_metrics = fastq_qc(validated.files)
                trimmed_read_metrics = fastq_qc(prepared.trimmed_reads)
                raw_count = int(raw_read_metrics["read_count"])
                reads_metrics = {
                    "raw": raw_read_metrics,
                    "trimmed": trimmed_read_metrics,
                    "retained_read_percent": round(
                        100.0 * int(trimmed_read_metrics["read_count"]) / raw_count, 3
                    ) if raw_count else 0.0,
                }
        else:
            assembly = prepare_assembly(validated, work_dir, config, runner)
            assembly_source = assembly.source
            assembly_metrics = assembly_qc(assembly.path) if assembly.path.is_file() else {}
            prokka = run_prokka(
                assembly.path, work_dir, raw_dir, validated.sample_id, config, runner
            )
            annotations_path = run_eggnog(
                prokka.faa, raw_dir, validated.sample_id, config, runner, warnings
            )
            if dry_run:
                header = ["query"]
                gene_rows = []
                term_rows = []
            else:
                header, gene_rows = parse_annotations(annotations_path)
                if not gene_rows:
                    warnings.append("eggNOG annotations contain a header but no gene rows.")
                term_rows = expand_terms(gene_rows, validated.sample_id)
                protein_count = count_fasta_records(prokka.faa)
        if dry_run:
            warnings.append("Dry-run planned commands; biological outputs were not executed.")
        wide_fields = ["sample_id", *header]
        wide_rows = [{"sample_id": validated.sample_id, **row} for row in gene_rows]
        write_tsv(output / "gene_annotations.tsv", wide_rows, wide_fields)
        write_tsv(output / "annotation_terms.tsv", term_rows, TERM_FIELDS)
        qc: dict[str, Any] = {
            "schema_version": "1.1",
            "analysis_mode": validated.analysis_mode,
            "input": {
                "type": validated.input_type,
                "paired": validated.paired,
                "file_count": len(validated.files),
                "compressed": list(validated.compressed),
            },
            "assembly": {"source": assembly_source, **assembly_metrics},
            "gene_prediction": {"status": "not_applicable"} if validated.analysis_mode == "reads" else {},
            "reads": reads_metrics,
            "annotation": {
                "gene_annotation_count": len(gene_rows),
                "term_count": len(term_rows),
            },
            "warnings": warnings,
        }
        if protein_count is not None:
            qc["gene_prediction"]["protein_count"] = protein_count
        write_json(output / "qc.json", qc)
        if validated.analysis_mode == "reads":
            tool_names = ("trimmomatic", "reads_search", "eggnog")
            search = config.value("tools", "reads_search")
            scientific_parameters = {
                "eggnog_mapper_version": config.value("tools", "eggnog", "version"),
                "search_mode": "diamond_blastx_then_no_search_annotation",
                "evalue": search["evalue"],
                "min_identity": search["min_identity"],
                "min_query_coverage": search["min_query_coverage"],
                "diamond_options": search.get("options", []),
                "trimmomatic_options": config.value("tools", "trimmomatic", "options"),
            }
        else:
            tool_names = ("trimmomatic", "assembler", "prokka", "eggnog")
            scientific_parameters = {
                "eggnog_mapper_version": config.value("tools", "eggnog", "version"),
                "search_mode": config.value("tools", "eggnog", "search_mode"),
                "trimmomatic_options": config.value("tools", "trimmomatic", "options"),
                "assembler_options": config.value("tools", "assembler", "options"),
                "prokka_options": config.value("tools", "prokka", "options"),
            }
        tool_records = {}
        for name in tool_names:
            section = config.value("tools", name)
            detected = "not_probed_dry_run" if dry_run else probe_version(
                section["executable"], section.get("prefix_options", [])
            )
            tool_records[name] = {
                "executable": str(section["executable"]),
                "version": detected,
            }
        manifest = {
            "schema_version": "1.1",
            "pipeline": "bacfunc",
            "pipeline_version": __version__,
            "started_at_utc": started,
            "ended_at_utc": utc_now(),
            "sample_id": validated.sample_id,
            "input_type": validated.input_type,
            "analysis_mode": validated.analysis_mode,
            "inputs": input_records(validated.files),
            "assembly_source": assembly_source,
            "threads": config.threads,
            "commands": render_commands(runner.commands),
            "tools": tool_records,
            "database": database_info
            or {"name": "eggNOG", "validation": "skipped_in_dry_run"},
            "database_manifest": deployed_manifest,
            "scientific_parameters": scientific_parameters,
            "runtime": runtime_record(),
            "warnings": warnings,
            "outputs": [
                "gene_annotations.tsv", "annotation_terms.tsv", "status.json",
                "manifest.json", "qc.json",
            ],
            "dry_run": dry_run,
        }
        write_json(output / "manifest.json", manifest)
        status = {
            "schema_version": "1.1",
            "status": "success",
            "pipeline": "bacfunc",
            "pipeline_version": __version__,
            "sample_id": validated.sample_id,
            "input_type": validated.input_type,
            "analysis_mode": validated.analysis_mode,
            "gene_annotation_count": len(gene_rows),
            "term_count": len(term_rows),
            "dry_run": dry_run,
            "warnings": warnings,
        }
        write_json(output / "status.json", status)
        with pipeline_log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"END bacfunc success {utc_now()}\n")
        if config.value("runtime", "keep_work", required=False) is False and not dry_run:
            shutil.rmtree(work_dir)
        return status
    except Exception as exc:
        _write_status(
            output,
            "failed",
            validated.sample_id,
            validated.input_type,
            validated.analysis_mode,
            dry_run,
            warnings,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        with pipeline_log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"END bacfunc failed {utc_now()} {type(exc).__name__}: {exc}\n")
        raise
