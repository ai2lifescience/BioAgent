"""Run Prokka and normalize its outputs for the BioAgent pipeline runner."""

from __future__ import annotations

import json
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
ALLOWED_FASTA_SUFFIXES = (".fa", ".fasta", ".fna")
SAFE_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
OUTPUT_FILES = {
    "gff_path": ("gff", "GFF3 annotation"),
    "gbk_path": ("gbk", "GenBank annotation"),
    "faa_path": ("faa", "Protein sequences"),
    "ffn_path": ("ffn", "Gene nucleotide sequences"),
    "fna_path": ("fna", "Annotated contigs"),
    "tsv_path": ("tsv", "Feature table"),
    "summary_path": ("txt", "Prokka statistics"),
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


def _validate_prefix(value: Any) -> str:
    prefix = _clean_text(value or "annotation", "prefix")
    if not SAFE_PREFIX.fullmatch(prefix):
        raise ValueError(
            "prefix must start with an alphanumeric character and contain only "
            "letters, numbers, dots, underscores, or hyphens."
        )
    return prefix


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


def _prokka_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else "unknown"


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
        f"- Tool: {metrics['tool']}",
        f"- Tool version: {metrics['tool_version']}",
        f"- Input genome: {metrics['input_path']}",
        f"- Input contigs: {metrics['input_contigs']}",
        f"- Input bases: {metrics['input_bases']}",
        f"- Prefix: {metrics['prefix']}",
        f"- Genus: {taxonomy['genus'] or 'not supplied'}",
        f"- Species: {taxonomy['species'] or 'not supplied'}",
        f"- Strain: {taxonomy['strain'] or 'not supplied'}",
        f"- CPUs: {metrics['cpus']}",
        f"- Runtime: {metrics['runtime_seconds']} seconds",
        "",
        "## Annotation summary",
        "",
    ]
    if summary:
        lines.extend(["| Metric | Value |", "|---|---:|"])
        lines.extend(
            f"| {key.replace('_', ' ')} | {value} |"
            for key, value in sorted(summary.items())
        )
    else:
        lines.append("Prokka did not emit parseable summary fields.")

    lines.extend(["", "## Output files", ""])
    for key, path in output_paths.items():
        lines.append(f"- {key}: `{path}`")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: str | Path) -> dict[str, Any]:
    """Execute one annotation run from a BioAgent runtime config."""
    resolved_config_path = Path(config_path).expanduser().resolve()
    config = _load_config(resolved_config_path)
    params = config.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("config params must be a mapping.")

    genome_path = _resolved_path(config.get("genome_path") or config.get("input_path"))
    input_contigs, input_bases = _validate_fasta(genome_path)

    output_dir = _resolved_path(
        config.get("output_dir"),
        resolved_config_path.parent / "output",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = _validate_prefix(params.get("prefix"))
    genus = _clean_text(params.get("genus"), "genus")
    species = _clean_text(params.get("species"), "species")
    strain = _clean_text(params.get("strain"), "strain")
    try:
        cpus = int(params.get("cpus", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("cpus must be an integer.") from exc
    if not 1 <= cpus <= 256:
        raise ValueError("cpus must be between 1 and 256.")

    output_paths = {
        key: _resolved_path(config.get(key), output_dir / f"annotation.{extension}")
        for key, (extension, _label) in OUTPUT_FILES.items()
    }
    output_paths.update(
        {
            "log_path": _resolved_path(config.get("log_path"), output_dir / "prokka.log"),
            "bundle_path": _resolved_path(
                config.get("bundle_path"),
                output_dir / "prokka_outputs.zip",
            ),
            "metrics_path": _resolved_path(config.get("metrics_path"), output_dir / "metrics.json"),
            "report_path": _resolved_path(config.get("report_path"), output_dir / "report.md"),
        }
    )
    for path in output_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    executable = shutil.which("prokka")
    if not executable:
        raise RuntimeError(
            "Prokka is not installed or is not available on PATH. Install a pinned "
            "Prokka environment before running the bacterial_annotation pipeline."
        )
    tool_version = _prokka_version(executable)

    started = perf_counter()
    with tempfile.TemporaryDirectory(prefix="prokka-", dir=output_dir) as raw_name:
        raw_output_dir = Path(raw_name)
        command = [
            executable,
            str(genome_path),
            "--outdir",
            str(raw_output_dir),
            "--prefix",
            prefix,
            "--cpus",
            str(cpus),
            "--force",
        ]
        for option, value in (("--genus", genus), ("--species", species), ("--strain", strain)):
            if value:
                command.extend([option, value])

        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        runtime_seconds = round(perf_counter() - started, 3)
        execution_log = "\n".join(
            [
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
                f"Prokka failed with exit code {completed.returncode}. "
                f"Execution log: {output_paths['log_path']}"
            )

        missing: list[str] = []
        for key, (extension, _label) in OUTPUT_FILES.items():
            source = raw_output_dir / f"{prefix}.{extension}"
            if not source.is_file():
                missing.append(str(source))
                continue
            shutil.copy2(source, output_paths[key])
        if missing:
            raise FileNotFoundError(
                "Prokka completed but did not create required output file(s): "
                + ", ".join(missing)
            )
        _write_bundle(raw_output_dir, output_paths["bundle_path"])

    annotation_summary = _summary_values(output_paths["summary_path"])
    metrics = {
        "status": "ok",
        "pipeline": PIPELINE_NAME,
        "tool": "Prokka",
        "tool_version": tool_version,
        "input_path": str(genome_path),
        "input_contigs": input_contigs,
        "input_bases": input_bases,
        "prefix": prefix,
        "taxonomy": {
            "genus": genus,
            "species": species,
            "strain": strain,
        },
        "cpus": cpus,
        "runtime_seconds": runtime_seconds,
        "annotation_summary": annotation_summary,
        "command": command,
        "outputs": {key: str(path) for key, path in output_paths.items()},
    }
    output_paths["metrics_path"].write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_report(output_paths["report_path"], metrics, output_paths)
    return metrics


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
