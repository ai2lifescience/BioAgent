"""Run Prokka or Bakta and normalize outputs for the BioAgent pipeline runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import Any
import zipfile

import yaml


PIPELINE_NAME = "bacterial_annotation"
ALLOWED_ANNOTATORS = {"prokka", "bakta"}
ALLOWED_FASTA_SUFFIXES = (".fa", ".fasta", ".fna")
ALLOWED_TRANSLATION_TABLES = {4, 11, 25}
ALLOWED_GRAM_VALUES = {"+", "-", "?"}
SAFE_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

REQUIRED_SOURCE_EXTENSIONS = {
    "prokka": {
        "gff_path": "gff",
        "gbk_path": "gbk",
        "faa_path": "faa",
        "ffn_path": "ffn",
        "fna_path": "fna",
        "tsv_path": "tsv",
        "summary_path": "txt",
    },
    "bakta": {
        "gff_path": "gff3",
        "gbk_path": "gbff",
        "faa_path": "faa",
        "ffn_path": "ffn",
        "fna_path": "fna",
        "tsv_path": "tsv",
        "summary_path": "txt",
    },
}

BAKTA_OPTIONAL_SOURCE_EXTENSIONS = {
    "bakta_json_path": "json",
    "inference_path": "inference.tsv",
    "hypotheticals_path": "hypotheticals.tsv",
    "plot_svg_path": "svg",
    "plot_png_path": "png",
}

OUTPUT_DEFAULTS = {
    "gff_path": "annotation.gff",
    "gbk_path": "annotation.gbk",
    "faa_path": "annotation.faa",
    "ffn_path": "annotation.ffn",
    "fna_path": "annotation.fna",
    "tsv_path": "annotation.tsv",
    "summary_path": "annotation.txt",
    "log_path": "annotation.log",
    "bundle_path": "annotation_outputs.zip",
    "metrics_path": "metrics.json",
    "report_path": "report.md",
    "bakta_json_path": "annotation.json",
    "inference_path": "annotation.inference.tsv",
    "hypotheticals_path": "annotation.hypotheticals.tsv",
    "plot_svg_path": "annotation.svg",
    "plot_png_path": "annotation.png",
}


def _load_config(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Pipeline config must be a YAML mapping: {path}")
    return dict(loaded)


def _resolved_path(value: Any, fallback: Path | None = None) -> Path:
    text = str(value or "").strip()
    if not text:
        if fallback is None:
            raise ValueError("Required path is missing from the runtime config.")
        return fallback.resolve()
    return Path(text).expanduser().resolve()


def _clean_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if any(character in text for character in ("\x00", "\r", "\n")):
        raise ValueError(f"{label} cannot contain control characters.")
    return text


def _safe_identifier(value: Any, label: str, default: str = "") -> str:
    identifier = _clean_text(value or default, label)
    if identifier and not SAFE_PREFIX.fullmatch(identifier):
        raise ValueError(
            f"{label} must start with an alphanumeric character and contain only "
            "letters, numbers, dots, underscores, or hyphens."
        )
    return identifier


def _as_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    raise ValueError(f"{label} must be true or false.")


def _validate_parameters(params: dict[str, Any]) -> dict[str, Any]:
    annotator = _clean_text(params.get("annotator") or "prokka", "annotator").lower()
    if annotator not in ALLOWED_ANNOTATORS:
        raise ValueError("annotator must be 'prokka' or 'bakta'.")

    try:
        cpus = int(params.get("cpus", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("cpus must be an integer.") from exc
    if not 1 <= cpus <= 256:
        raise ValueError("cpus must be between 1 and 256.")

    try:
        translation_table = int(params.get("translation_table", 11))
    except (TypeError, ValueError) as exc:
        raise ValueError("translation_table must be an integer.") from exc
    if translation_table not in ALLOWED_TRANSLATION_TABLES:
        allowed = ", ".join(str(value) for value in sorted(ALLOWED_TRANSLATION_TABLES))
        raise ValueError(f"translation_table must be one of: {allowed}.")

    gram = _clean_text(params.get("gram") or "?", "gram")
    if gram not in ALLOWED_GRAM_VALUES:
        raise ValueError("gram must be '+', '-', or '?'.")

    validated = {
        "annotator": annotator,
        "prefix": _safe_identifier(params.get("prefix"), "prefix", "annotation"),
        "genus": _clean_text(params.get("genus"), "genus"),
        "species": _clean_text(params.get("species"), "species"),
        "strain": _clean_text(params.get("strain"), "strain"),
        "cpus": cpus,
        "translation_table": translation_table,
        "locus_tag": _safe_identifier(params.get("locus_tag"), "locus_tag"),
        "compliant": _as_bool(params.get("compliant", False), "compliant"),
        "gram": gram,
        "meta": _as_bool(params.get("meta", False), "meta"),
        "complete": _as_bool(params.get("complete", False), "complete"),
        "keep_contig_headers": _as_bool(
            params.get("keep_contig_headers", False),
            "keep_contig_headers",
        ),
        "rfam": _as_bool(params.get("rfam", False), "rfam"),
    }

    configured_db_path = _clean_text(params.get("bakta_db_path"), "bakta_db_path")
    if annotator == "prokka":
        if configured_db_path or gram != "?" or validated["meta"] or validated["complete"]:
            raise ValueError(
                "bakta_db_path, gram, meta, and complete are only valid when "
                "annotator is 'bakta'."
            )
        if validated["keep_contig_headers"]:
            raise ValueError(
                "keep_contig_headers is only valid when annotator is 'bakta'."
            )
        validated["bakta_db_path"] = ""
    else:
        if validated["rfam"]:
            raise ValueError("rfam is only valid when annotator is 'prokka'.")
        if validated["meta"] and validated["complete"]:
            raise ValueError("meta and complete cannot both be true.")
        raw_db_path = configured_db_path or _clean_text(
            os.getenv("BAKTA_DB", ""),
            "BAKTA_DB",
        )
        if not raw_db_path:
            raise ValueError(
                "Bakta requires bakta_db_path or the BAKTA_DB environment variable."
            )
        db_path = Path(raw_db_path).expanduser().resolve()
        if not db_path.is_dir():
            raise FileNotFoundError(f"Bakta database directory not found: {db_path}")
        validated["bakta_db_path"] = str(db_path)
    return validated


def _validate_fasta(path: Path) -> tuple[int, int]:
    if not path.is_file():
        raise FileNotFoundError(f"Genome FASTA not found: {path}")
    if path.suffix.lower() not in ALLOWED_FASTA_SUFFIXES:
        allowed = ", ".join(ALLOWED_FASTA_SUFFIXES)
        raise ValueError(f"Genome input must use one of these suffixes: {allowed}.")

    record_count = 0
    base_count = 0
    seen_header = False
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if not line[1:].strip():
                raise ValueError(f"Empty FASTA header at line {line_number}: {path}")
            record_count += 1
            seen_header = True
            continue
        if not seen_header:
            raise ValueError(f"Sequence content appears before the first FASTA header: {path}")
        base_count += len(re.sub(r"\s+", "", line))

    if record_count == 0 or base_count == 0:
        raise ValueError(f"Genome FASTA contains no sequence records: {path}")
    return record_count, base_count


def _tool_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else "unknown"


def _build_prokka_command(
    executable: str,
    genome_path: Path,
    raw_output_dir: Path,
    params: dict[str, Any],
) -> list[str]:
    command = [
        executable,
        str(genome_path),
        "--outdir",
        str(raw_output_dir),
        "--prefix",
        params["prefix"],
        "--cpus",
        str(params["cpus"]),
        "--gcode",
        str(params["translation_table"]),
        "--force",
    ]
    for option, value in (
        ("--genus", params["genus"]),
        ("--species", params["species"]),
        ("--strain", params["strain"]),
        ("--locustag", params["locus_tag"]),
    ):
        if value:
            command.extend([option, value])
    if params["compliant"]:
        command.append("--compliant")
    if params["rfam"]:
        command.append("--rfam")
    return command


def _build_bakta_command(
    executable: str,
    genome_path: Path,
    raw_output_dir: Path,
    params: dict[str, Any],
) -> list[str]:
    command = [
        executable,
        str(genome_path),
        "--db",
        params["bakta_db_path"],
        "--output",
        str(raw_output_dir),
        "--prefix",
        params["prefix"],
        "--threads",
        str(params["cpus"]),
        "--translation-table",
        str(params["translation_table"]),
        "--gram",
        params["gram"],
        "--force",
    ]
    for option, value in (
        ("--genus", params["genus"]),
        ("--species", params["species"]),
        ("--strain", params["strain"]),
        ("--locus-tag", params["locus_tag"]),
    ):
        if value:
            command.extend([option, value])
    for enabled, option in (
        (params["compliant"], "--compliant"),
        (params["meta"], "--meta"),
        (params["complete"], "--complete"),
        (params["keep_contig_headers"], "--keep-contig-headers"),
    ):
        if enabled:
            command.append(option)
    return command


def _summary_values(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in raw_line:
            continue
        raw_key, raw_value = raw_line.split(":", 1)
        key = re.sub(r"[^A-Za-z0-9]+", "_", raw_key.strip()).strip("_").lower()
        value = raw_value.strip()
        if not key or not value:
            continue
        if re.fullmatch(r"[-+]?\d+", value):
            values[key] = int(value)
        elif re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", value):
            values[key] = float(value)
        else:
            values[key] = value
    return values


def _bakta_json_details(path: Path) -> tuple[dict[str, Any], str, str]:
    if not path.is_file():
        return {}, "", ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, "", ""
    if not isinstance(payload, dict):
        return {}, "", ""

    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    version = payload.get("version")
    database = payload.get("database")
    database_version = ""
    database_type = ""
    database_version = str(
        payload.get("dbVersion")
        or payload.get("databaseVersion")
        or ""
    )
    database_type = str(payload.get("dbType") or payload.get("databaseType") or "")
    if isinstance(version, dict):
        database_version = str(
            version.get("db")
            or version.get("database")
            or version.get("databaseVersion")
            or ""
        )
        database_type = str(version.get("dbType") or version.get("databaseType") or "")
    if isinstance(database, dict):
        database_version = database_version or str(database.get("version") or "")
        database_type = database_type or str(database.get("type") or "")
    return dict(stats), database_version, database_type


def _bakta_log_database_details(text: str) -> tuple[str, str]:
    match = re.search(
        r"^\s*db:\s*.+?,\s*version\s+([^,\s]+),\s*([^,\s]+)",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _copy_annotation_outputs(
    annotator: str,
    prefix: str,
    raw_output_dir: Path,
    output_paths: dict[str, Path],
) -> list[str]:
    missing: list[str] = []
    for key, extension in REQUIRED_SOURCE_EXTENSIONS[annotator].items():
        source = raw_output_dir / f"{prefix}.{extension}"
        if not source.is_file():
            missing.append(str(source))
            continue
        shutil.copy2(source, output_paths[key])

    if annotator == "bakta":
        for key, extension in BAKTA_OPTIONAL_SOURCE_EXTENSIONS.items():
            source = raw_output_dir / f"{prefix}.{extension}"
            if source.is_file():
                shutil.copy2(source, output_paths[key])
    return missing


def _write_bundle(raw_output_dir: Path, bundle_path: Path) -> None:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(raw_output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(raw_output_dir))


def _write_report(
    report_path: Path,
    metrics: dict[str, Any],
    output_paths: dict[str, Path],
) -> None:
    taxonomy = metrics["taxonomy"]
    summary = metrics["annotation_summary"]
    lines = [
        "# Bacterial Genome Annotation Report",
        "",
        f"- Status: {metrics['status']}",
        f"- Annotator: {metrics['annotator']}",
        f"- Tool: {metrics['tool']}",
        f"- Tool version: {metrics['tool_version']}",
        f"- Input genome: {metrics['input_path']}",
        f"- Input contigs: {metrics['input_contigs']}",
        f"- Input bases: {metrics['input_bases']}",
        f"- Prefix: {metrics['prefix']}",
        f"- Genus: {taxonomy['genus'] or 'not supplied'}",
        f"- Species: {taxonomy['species'] or 'not supplied'}",
        f"- Strain: {taxonomy['strain'] or 'not supplied'}",
        f"- Translation table: {metrics['translation_table']}",
        f"- CPUs: {metrics['cpus']}",
        f"- Runtime: {metrics['runtime_seconds']} seconds",
    ]
    if metrics.get("database_path"):
        lines.append(f"- Bakta database: {metrics['database_path']}")
        lines.append(f"- Bakta database version: {metrics.get('database_version') or 'unknown'}")
        lines.append(f"- Bakta database type: {metrics.get('database_type') or 'unknown'}")
    lines.extend(["", "## Annotation summary", ""])
    if summary:
        lines.extend(["| Metric | Value |", "|---|---:|"])
        lines.extend(
            f"| {key.replace('_', ' ')} | {value} |"
            for key, value in sorted(summary.items())
        )
    else:
        lines.append(f"{metrics['tool']} did not emit parseable summary fields.")

    lines.extend(["", "## Output files", ""])
    for key, path in output_paths.items():
        if path.exists():
            lines.append(f"- {key}: `{path}`")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: str | Path) -> dict[str, Any]:
    """Execute one Prokka or Bakta annotation from a BioAgent runtime config."""
    resolved_config_path = Path(config_path).expanduser().resolve()
    config = _load_config(resolved_config_path)
    raw_params = config.get("params") or {}
    if not isinstance(raw_params, dict):
        raise ValueError("config params must be a mapping.")
    params = _validate_parameters(raw_params)

    genome_path = _resolved_path(config.get("genome_path") or config.get("input_path"))
    input_contigs, input_bases = _validate_fasta(genome_path)
    output_dir = _resolved_path(
        config.get("output_dir"),
        resolved_config_path.parent / "output",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        key: _resolved_path(config.get(key), output_dir / filename)
        for key, filename in OUTPUT_DEFAULTS.items()
    }
    for path in output_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    annotator = params["annotator"]
    executable = shutil.which(annotator)
    if not executable:
        display_name = "Prokka" if annotator == "prokka" else "Bakta"
        raise RuntimeError(
            f"{display_name} is not installed or is not available on PATH. "
            f"Install {display_name} before running with annotator '{annotator}'."
        )
    tool_name = "Prokka" if annotator == "prokka" else "Bakta"
    tool_version = _tool_version(executable)

    started = perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"{annotator}-", dir=output_dir) as raw_name:
        raw_output_dir = Path(raw_name)
        if annotator == "prokka":
            command = _build_prokka_command(executable, genome_path, raw_output_dir, params)
        else:
            command = _build_bakta_command(executable, genome_path, raw_output_dir, params)

        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        runtime_seconds = round(perf_counter() - started, 3)
        execution_log = "\n".join(
            [
                f"Annotator: {annotator}",
                f"Tool version: {tool_version}",
                f"Command: {shlex.join(command)}",
                f"Return code: {completed.returncode}",
                "",
                "STDOUT",
                completed.stdout or "",
                "",
                "STDERR",
                completed.stderr or "",
            ]
        )
        output_paths["log_path"].write_text(execution_log, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"{tool_name} failed with exit code {completed.returncode}. "
                f"Execution log: {output_paths['log_path']}"
            )

        missing = _copy_annotation_outputs(
            annotator,
            params["prefix"],
            raw_output_dir,
            output_paths,
        )
        if missing:
            raise FileNotFoundError(
                f"{tool_name} completed but did not create required output file(s): "
                + ", ".join(missing)
            )
        _write_bundle(raw_output_dir, output_paths["bundle_path"])

    annotation_summary = _summary_values(output_paths["summary_path"])
    database_version = ""
    database_type = ""
    if annotator == "bakta":
        bakta_stats, database_version, database_type = _bakta_json_details(
            output_paths["bakta_json_path"]
        )
        log_database_version, log_database_type = _bakta_log_database_details(
            "\n".join([completed.stdout or "", completed.stderr or ""])
        )
        database_version = database_version or log_database_version
        database_type = database_type or log_database_type
        if bakta_stats:
            annotation_summary = bakta_stats

    metrics = {
        "status": "ok",
        "pipeline": PIPELINE_NAME,
        "annotator": annotator,
        "tool": tool_name,
        "tool_version": tool_version,
        "database_path": params.get("bakta_db_path") or "",
        "database_version": database_version,
        "database_type": database_type,
        "input_path": str(genome_path),
        "input_contigs": input_contigs,
        "input_bases": input_bases,
        "prefix": params["prefix"],
        "taxonomy": {
            "genus": params["genus"],
            "species": params["species"],
            "strain": params["strain"],
        },
        "cpus": params["cpus"],
        "translation_table": params["translation_table"],
        "locus_tag": params["locus_tag"],
        "compliant": params["compliant"],
        "meta": params["meta"],
        "complete": params["complete"],
        "runtime_seconds": runtime_seconds,
        "annotation_summary": annotation_summary,
        "command": command,
        "outputs": {
            key: str(path)
            for key, path in output_paths.items()
            if path.exists() or key in {"metrics_path", "report_path"}
        },
    }
    output_paths["metrics_path"].write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_report(output_paths["report_path"], metrics, output_paths)
    return metrics


def annotate_bacterial_genome(config_path: str | Path) -> dict[str, Any]:
    """Public pipeline entry point for bacterial genome annotation."""
    return run(config_path)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: workflow.py <config.runtime.yaml>", file=sys.stderr)
        return 2
    try:
        run(sys.argv[1])
    except Exception as exc:
        print(f"bacterial_annotation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
