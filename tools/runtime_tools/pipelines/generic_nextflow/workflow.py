"""Dependency-light analysis step used by the generic Nextflow workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import yaml


def clean_fasta_sequence(path: Path) -> str:
    parts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith(">"):
            continue
        parts.append(re.sub(r"[^A-Za-z*-]", "", value).upper())
    return "".join(parts)


def metadata_rows(path: Path) -> int:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return max(0, len(lines) - 1)


def write_normalized_fasta(path: Path, label: str, segment: str, sequence: str) -> None:
    lines = [f">{label}|{segment}"]
    lines.extend(sequence[index : index + 80] for index in range(0, len(sequence), 80))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config: dict[str, Any], input_path: Path, metadata_path: Path) -> dict[str, Any]:
    settings = config.get("params") if isinstance(config.get("params"), dict) else {}
    label = str(config.get("label") or "generic_nextflow")
    segment = str(settings.get("segment") or "segment1")
    sequence = clean_fasta_sequence(input_path)
    min_length = int(settings.get("min_length") or 0)
    metrics = {
        "status": "ok",
        "pipeline": "generic_nextflow",
        "label": label,
        "analysis_mode": str(settings.get("analysis_mode") or "example"),
        "subtype": str(settings.get("subtype") or ""),
        "segment": segment,
        "time": str(settings.get("time") or ""),
        "metadata_rows": metadata_rows(metadata_path),
        "sequence_length": len(sequence),
        "passes_min_length": len(sequence) >= min_length,
        "min_length": min_length,
        "gc_percent": round(
            ((sequence.count("G") + sequence.count("C")) / len(sequence) * 100)
            if sequence
            else 0,
            2,
        ),
    }

    write_normalized_fasta(Path("normalized.fasta"), label, segment, sequence)
    Path("metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    report_lines = [
        "# Generic Nextflow Pipeline Report",
        "",
        f"- Label: {label}",
        f"- Input: {input_path}",
        f"- Metadata: {metadata_path}",
        f"- Analysis mode: {metrics['analysis_mode']}",
        f"- Subtype: {metrics['subtype']}",
        f"- Segment: {metrics['segment']}",
        f"- Time: {metrics['time']}",
        f"- Metadata rows: {metrics['metadata_rows']}",
        f"- Sequence length: {metrics['sequence_length']}",
        f"- Minimum length: {metrics['min_length']}",
        f"- Passes minimum length: {metrics['passes_min_length']}",
        f"- GC percent: {metrics['gc_percent']}",
    ]
    Path("report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    run(config, args.input, args.metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
