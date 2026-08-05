"""End-to-end BacARG orchestration."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .abricate import ARG_FIELDS, enrich_hits, parse_abricate, run_abricate
from .assembly import prepare_assembly, prepare_reads
from .command import CommandRunner, render_commands
from .config import PipelineConfig, load_config
from .database import validate_database
from .gff import add_context, load_cds
from .input import InputSet, validate_inputs
from .manifest import database_manifest, input_records, runtime_record, utc_now
from .metadata import load_metadata
from .outputs import write_json, write_jsonl, write_tsv
from .prokka import run_prokka
from .qc import assembly_qc, count_fasta_records, fastq_qc
from .read_mapping import parse_paf, run_minimap2
from .versions import probe_version


def _status(
    output: Path,
    *,
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
        "pipeline": "bacarg",
        "pipeline_version": __version__,
        "sample_id": sample_id,
        "input_type": input_type,
        "analysis_mode": analysis_mode,
        "dry_run": dry_run,
        "warnings": warnings,
    }
    payload.update(extra)
    write_json(output / "status.json", payload)


def _database_version(config: PipelineConfig, deployed: dict[str, Any] | None) -> str:
    if deployed:
        for key in ("database_version", "version"):
            if deployed.get(key):
                return str(deployed[key])
    return str(config.value("tools", "abricate", "database_version", required=False) or "")


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
    """Run BacARG and return the success status payload."""
    output = Path(output).expanduser().resolve()
    validated: InputSet = validate_inputs(
        inputs,
        output,
        sample_id,
        input_type=input_type,
        analysis_mode=analysis_mode,
    )
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "raw"
    logs_dir = output / "logs"
    work_dir = output / "work"
    for directory in (raw_dir, logs_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    started = utc_now()
    pipeline_log = logs_dir / "pipeline.log"
    pipeline_log.write_text(f"START bacarg {started}\n", encoding="utf-8")
    runner = CommandRunner(dry_run=dry_run)
    _status(
        output,
        status="running",
        sample_id=validated.sample_id,
        input_type=validated.input_type,
        analysis_mode=validated.analysis_mode,
        dry_run=dry_run,
        warnings=warnings,
    )
    try:
        config = load_config(config_path)
        if threads is not None:
            from dataclasses import replace
            config = replace(config, threads=threads)
        deployed_manifest = database_manifest(
            config.database_path("manifest", required=False), warnings
        )
        if config.value("runtime", "strict_manifest", required=False) and deployed_manifest is None:
            raise RuntimeError("A database manifest is required by runtime.strict_manifest.")
        database_info: dict[str, Any] | None = None
        metadata: dict[str, dict[str, str]] = {}
        if not dry_run:
            database_info = validate_database(config)
            metadata = load_metadata(
                config.database_path("metadata"),
                config.value("metadata_fields", required=False),
            )
        database_name = str(config.value("tools", "abricate", "database_name"))
        assembly_source = "not_applicable"
        assembly_metrics: dict[str, Any] = {}
        protein_count: int | None = None
        reads_metrics: dict[str, Any] = {}
        if validated.analysis_mode == "reads":
            prepared = prepare_reads(validated, work_dir, config, runner)
            raw_paf = raw_dir / f"minimap2_{database_name}.paf"
            run_minimap2(prepared.trimmed_reads, raw_paf, config, runner)
            if dry_run:
                rows: list[dict[str, Any]] = []
            else:
                rows = enrich_hits(
                    parse_paf(raw_paf, config),
                    metadata,
                    validated.sample_id,
                    database_name,
                    _database_version(config, deployed_manifest),
                    warnings,
                )
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
            if assembly.path.is_file():
                assembly_metrics = assembly_qc(assembly.path)
            prokka = run_prokka(
                assembly.path, work_dir, raw_dir, validated.sample_id, config, runner
            )
            raw_abricate = raw_dir / f"abricate_{database_name}.tsv"
            run_abricate(assembly.path, raw_abricate, config, runner)
            if dry_run:
                rows = []
            else:
                rows = enrich_hits(
                    parse_abricate(raw_abricate),
                    metadata,
                    validated.sample_id,
                    database_name,
                    _database_version(config, deployed_manifest),
                    warnings,
                )
                rows = add_context(rows, load_cds(prokka.gff))
                protein_count = count_fasta_records(prokka.faa)
        if dry_run:
            warnings.append("Dry-run planned commands; biological outputs were not executed.")
        write_tsv(output / "arg_hits.tsv", rows, ARG_FIELDS)
        write_jsonl(output / "arg_hits.jsonl", rows)
        qc_payload: dict[str, Any] = {
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
            "annotation": {"hit_count": len(rows)},
            "warnings": warnings,
        }
        if protein_count is not None:
            qc_payload["gene_prediction"]["protein_count"] = protein_count
        write_json(output / "qc.json", qc_payload)
        finished = utc_now()
        output_files = [
            "arg_hits.tsv", "arg_hits.jsonl", "status.json", "manifest.json", "qc.json"
        ]
        if validated.analysis_mode == "reads":
            tool_names = ("trimmomatic", "reads_mapper")
            mapper = config.value("tools", "reads_mapper")
            scientific_parameters = {
                "min_identity": mapper["min_identity"],
                "min_coverage": mapper["min_coverage"],
                "min_mapq": mapper["min_mapq"],
                "min_alignment_length": mapper["min_alignment_length"],
                "min_supporting_reads": mapper["min_supporting_reads"],
                "trimmomatic_options": config.value("tools", "trimmomatic", "options"),
                "mapper_options": mapper.get("options", []),
            }
        else:
            tool_names = ("trimmomatic", "assembler", "prokka", "abricate")
            scientific_parameters = {
                "min_identity": config.value("tools", "abricate", "min_identity"),
                "min_coverage": config.value("tools", "abricate", "min_coverage"),
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
        manifest_payload = {
            "schema_version": "1.1",
            "pipeline": "bacarg",
            "pipeline_version": __version__,
            "started_at_utc": started,
            "ended_at_utc": finished,
            "sample_id": validated.sample_id,
            "input_type": validated.input_type,
            "analysis_mode": validated.analysis_mode,
            "inputs": input_records(validated.files),
            "assembly_source": assembly_source,
            "threads": config.threads,
            "commands": render_commands(runner.commands),
            "tools": tool_records,
            "database": database_info
            or {"name": database_name, "validation": "skipped_in_dry_run"},
            "database_manifest": deployed_manifest,
            "scientific_parameters": scientific_parameters,
            "runtime": runtime_record(),
            "warnings": warnings,
            "outputs": output_files,
            "dry_run": dry_run,
        }
        write_json(output / "manifest.json", manifest_payload)
        final_status = {
            "schema_version": "1.1",
            "status": "success",
            "pipeline": "bacarg",
            "pipeline_version": __version__,
            "sample_id": validated.sample_id,
            "input_type": validated.input_type,
            "analysis_mode": validated.analysis_mode,
            "hit_count": len(rows),
            "dry_run": dry_run,
            "warnings": warnings,
        }
        write_json(output / "status.json", final_status)
        with pipeline_log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"END bacarg success {finished}\n")
        keep_work = config.value("runtime", "keep_work", required=False)
        if keep_work is False and not dry_run:
            shutil.rmtree(work_dir)
        return final_status
    except Exception as exc:
        _status(
            output,
            status="failed",
            sample_id=validated.sample_id,
            input_type=validated.input_type,
            analysis_mode=validated.analysis_mode,
            dry_run=dry_run,
            warnings=warnings,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        with pipeline_log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"END bacarg failed {utc_now()} {type(exc).__name__}: {exc}\n")
        raise
