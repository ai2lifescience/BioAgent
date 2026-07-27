"""Predict RNA minimum-free-energy structures with ViennaRNA RNAfold."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import shlex
import shutil
import statistics
import subprocess
import sys
from time import perf_counter
from typing import Any

import yaml


PIPELINE_NAME = "rna_secondary_structure"
ALLOWED_FASTA_SUFFIXES = (".fa", ".fasta", ".fna")
IUPAC_NUCLEOTIDES = frozenset("ACGUTRYSWKMBDHVN")
MAX_RECORDS = 1000
STRUCTURE_LINE = re.compile(
    r"^([().]+)\s+\(\s*([-+]?\d+(?:\.\d+)?)\s*\)\s*$"
)


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


def _validated_parameters(params: dict[str, Any]) -> tuple[float, int]:
    try:
        temperature = float(params.get("temperature_c", 37.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("temperature_c must be a number.") from exc
    if not -100.0 <= temperature <= 100.0:
        raise ValueError("temperature_c must be between -100 and 100.")
    try:
        max_length = int(params.get("max_sequence_length", 10000))
    except (TypeError, ValueError) as exc:
        raise ValueError("max_sequence_length must be an integer.") from exc
    if not 1 <= max_length <= 1_000_000:
        raise ValueError("max_sequence_length must be between 1 and 1000000.")
    return temperature, max_length


def _read_fasta(path: Path, max_length: int) -> list[tuple[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"RNA FASTA not found: {path}")
    if path.suffix.lower() not in ALLOWED_FASTA_SUFFIXES:
        allowed = ", ".join(ALLOWED_FASTA_SUFFIXES)
        raise ValueError(f"RNA input must use one of these suffixes: {allowed}.")

    records: list[tuple[str, str]] = []
    current_id: str | None = None
    sequence_parts: list[str] = []
    seen_ids: set[str] = set()

    def append_record() -> None:
        if current_id is None:
            return
        sequence = "".join(sequence_parts).upper().replace("T", "U")
        if not sequence:
            raise ValueError(f"FASTA record '{current_id}' has no sequence.")
        invalid = sorted(set(sequence) - IUPAC_NUCLEOTIDES)
        if invalid:
            raise ValueError(
                f"FASTA record '{current_id}' contains unsupported nucleotide symbols: "
                + ", ".join(invalid)
            )
        if len(sequence) > max_length:
            raise ValueError(
                f"FASTA record '{current_id}' is {len(sequence)} nt; the configured "
                f"maximum is {max_length} nt."
            )
        records.append((current_id, sequence))

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig", errors="strict").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            append_record()
            header = line[1:].strip()
            identifier = header.split(maxsplit=1)[0] if header else ""
            if not identifier:
                raise ValueError(f"Empty FASTA header at line {line_number}: {path}")
            if any(character in identifier for character in ("\x00", "\r", "\n", "\t")):
                raise ValueError(f"Invalid control character in FASTA identifier at line {line_number}.")
            if identifier in seen_ids:
                raise ValueError(f"Duplicate FASTA identifier: {identifier}")
            if len(records) >= MAX_RECORDS:
                raise ValueError(f"RNA FASTA may contain at most {MAX_RECORDS} records.")
            seen_ids.add(identifier)
            current_id = identifier
            sequence_parts = []
            continue
        if current_id is None:
            raise ValueError(f"Sequence content appears before the first FASTA header: {path}")
        sequence_parts.append(re.sub(r"\s+", "", line))

    append_record()
    if not records:
        raise ValueError(f"RNA FASTA contains no sequence records: {path}")
    return records


def _rnafold_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else "unknown"


def _parse_rnafold_output(stdout: str, identifier: str, expected_length: int) -> tuple[str, float]:
    for raw_line in reversed(stdout.splitlines()):
        match = STRUCTURE_LINE.fullmatch(raw_line.strip())
        if not match:
            continue
        structure = match.group(1)
        if len(structure) != expected_length:
            raise RuntimeError(
                f"RNAfold returned a structure of length {len(structure)} for "
                f"'{identifier}', expected {expected_length}."
            )
        return structure, float(match.group(2))
    raise RuntimeError(f"Could not parse RNAfold output for FASTA record '{identifier}'.")


def _write_structures(
    structures_path: Path,
    dot_bracket_path: Path,
    predictions: list[dict[str, Any]],
) -> None:
    with structures_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["sequence_id", "length_nt", "mfe_kcal_mol", "dot_bracket"])
        for prediction in predictions:
            writer.writerow(
                [
                    prediction["sequence_id"],
                    prediction["length_nt"],
                    f"{prediction['mfe_kcal_mol']:.2f}",
                    prediction["dot_bracket"],
                ]
            )

    lines: list[str] = []
    for prediction in predictions:
        lines.extend(
            [
                f">{prediction['sequence_id']}",
                prediction["sequence"],
                f"{prediction['dot_bracket']} ({prediction['mfe_kcal_mol']:.2f})",
            ]
        )
    dot_bracket_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_report(report_path: Path, metrics: dict[str, Any], structures_path: Path) -> None:
    lines = [
        "# RNA Secondary Structure Prediction Report",
        "",
        f"- Status: {metrics['status']}",
        f"- Tool: {metrics['tool']}",
        f"- Tool version: {metrics['tool_version']}",
        f"- Input: {metrics['input_path']}",
        f"- Sequences: {metrics['sequence_count']}",
        f"- Total nucleotides: {metrics['total_nt']}",
        f"- Temperature: {metrics['temperature_c']} °C",
        f"- Mean MFE: {metrics['mean_mfe_kcal_mol']} kcal/mol",
        f"- Minimum MFE: {metrics['minimum_mfe_kcal_mol']} kcal/mol",
        f"- Runtime: {metrics['runtime_seconds']} seconds",
        "",
        "## Predictions",
        "",
        "| Sequence | Length (nt) | MFE (kcal/mol) | Dot-bracket |",
        "|---|---:|---:|---|",
    ]
    for prediction in metrics["predictions"]:
        lines.append(
            f"| {prediction['sequence_id']} | {prediction['length_nt']} | "
            f"{prediction['mfe_kcal_mol']:.2f} | `{prediction['dot_bracket']}` |"
        )
    lines.extend(["", f"Full table: `{structures_path}`"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: str | Path) -> dict[str, Any]:
    """Execute RNAfold for each record in one FASTA input."""
    resolved_config_path = Path(config_path).expanduser().resolve()
    config = _load_config(resolved_config_path)
    params = config.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("config params must be a mapping.")
    temperature, max_length = _validated_parameters(params)

    rna_path = _resolved_path(config.get("rna_path") or config.get("input_path"))
    records = _read_fasta(rna_path, max_length)
    output_dir = _resolved_path(config.get("output_dir"), resolved_config_path.parent / "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "report_path": _resolved_path(config.get("report_path"), output_dir / "report.md"),
        "metrics_path": _resolved_path(config.get("metrics_path"), output_dir / "metrics.json"),
        "structures_path": _resolved_path(
            config.get("structures_path"), output_dir / "structures.tsv"
        ),
        "dot_bracket_path": _resolved_path(
            config.get("dot_bracket_path"), output_dir / "structures.dbn"
        ),
        "log_path": _resolved_path(config.get("log_path"), output_dir / "rnafold.log"),
    }
    for path in output_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    executable = shutil.which("RNAfold")
    if not executable:
        raise RuntimeError(
            "RNAfold is not installed or is not available on PATH. Install ViennaRNA "
            "before running the rna_secondary_structure pipeline."
        )
    tool_version = _rnafold_version(executable)
    command = [executable, "--noPS", "--temp", str(temperature)]
    started = perf_counter()
    predictions: list[dict[str, Any]] = []
    log_sections: list[str] = [f"RNAfold version: {tool_version}"]
    for identifier, sequence in records:
        completed = subprocess.run(
            command,
            input=f">{identifier}\n{sequence}\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        log_sections.extend(
            [
                "",
                f"Record: {identifier}",
                f"Command: {shlex.join(command)}",
                f"Return code: {completed.returncode}",
                "STDOUT",
                completed.stdout or "",
                "STDERR",
                completed.stderr or "",
            ]
        )
        if completed.returncode != 0:
            output_paths["log_path"].write_text("\n".join(log_sections), encoding="utf-8")
            raise RuntimeError(
                f"RNAfold failed for '{identifier}' with exit code {completed.returncode}. "
                f"Execution log: {output_paths['log_path']}"
            )
        structure, mfe = _parse_rnafold_output(completed.stdout or "", identifier, len(sequence))
        predictions.append(
            {
                "sequence_id": identifier,
                "sequence": sequence,
                "length_nt": len(sequence),
                "dot_bracket": structure,
                "mfe_kcal_mol": mfe,
            }
        )

    runtime_seconds = round(perf_counter() - started, 3)
    output_paths["log_path"].write_text("\n".join(log_sections) + "\n", encoding="utf-8")
    _write_structures(
        output_paths["structures_path"],
        output_paths["dot_bracket_path"],
        predictions,
    )
    energies = [prediction["mfe_kcal_mol"] for prediction in predictions]
    metrics = {
        "status": "ok",
        "pipeline": PIPELINE_NAME,
        "tool": "ViennaRNA RNAfold",
        "tool_version": tool_version,
        "input_path": str(rna_path),
        "sequence_count": len(predictions),
        "total_nt": sum(item["length_nt"] for item in predictions),
        "temperature_c": temperature,
        "max_sequence_length": max_length,
        "mean_mfe_kcal_mol": round(statistics.fmean(energies), 3),
        "minimum_mfe_kcal_mol": min(energies),
        "runtime_seconds": runtime_seconds,
        "command": command,
        "predictions": [
            {key: value for key, value in prediction.items() if key != "sequence"}
            for prediction in predictions
        ],
        "outputs": {key: str(path) for key, path in output_paths.items()},
    }
    output_paths["metrics_path"].write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_report(output_paths["report_path"], metrics, output_paths["structures_path"])
    return metrics


def predict_rna_secondary_structure(config_path: str | Path) -> dict[str, Any]:
    """Public entry point for the Biomni-style RNA folding capability."""
    return run(config_path)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: workflow.py <config.runtime.yaml>", file=sys.stderr)
        return 2
    try:
        run(sys.argv[1])
    except Exception as exc:
        print(f"rna_secondary_structure failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
