"""Small deterministic FASTQ example; sequences are synthetic teaching data."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys

import yaml


def run(config: dict) -> dict:
    params = config.get("params", {})
    minimum = int(params.get("min_length", 6))
    max_n = float(params.get("max_n_fraction", 0.25))
    if minimum < 1 or not math.isfinite(max_n) or not 0 <= max_n <= 1:
        raise ValueError("min_length must be positive; max_n_fraction must be between 0 and 1.")
    metadata = {}
    with Path(config["metadata_path"]).open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not {"read_id", "sample"} <= set(reader.fieldnames or []):
            raise ValueError("Metadata requires read_id and sample columns.")
        for row in reader:
            identifier = row["read_id"]
            if not identifier or identifier in metadata:
                raise ValueError("Metadata contains an empty or duplicate read_id.")
            metadata[identifier] = row["sample"]
    records, seen = [], set()
    with Path(config["input_path"]).open() as handle:
        while header := handle.readline():
            sequence, plus, quality = (handle.readline().rstrip("\r\n") for _ in range(3))
            if not header.startswith("@") or not plus.startswith("+") or not sequence or len(sequence) != len(quality):
                raise ValueError("Malformed FASTQ record: header, separator, sequence, or quality length.")
            identifier = header[1:].strip().split()[0]
            if identifier in seen or set(sequence.upper()) - set("ACGTN"):
                raise ValueError("FASTQ has duplicate IDs or unsupported sequence characters.")
            if any(ord(c) < 33 or ord(c) > 126 for c in quality):
                raise ValueError("FASTQ quality must be printable Phred+33 text.")
            seen.add(identifier)
            sequence = sequence.upper()
            passed = len(sequence) >= minimum and sequence.count("N") / len(sequence) <= max_n
            records.append((identifier, sequence, quality, passed))
    if not records:
        raise ValueError("No FASTQ records were found.")
    for key in ("metrics_path", "report_path", "assignments_path", "filtered_path"):
        Path(config[key]).parent.mkdir(parents=True, exist_ok=True)
    with Path(config["filtered_path"]).open("w") as filtered, Path(config["assignments_path"]).open("w", newline="") as table:
        writer = csv.writer(table, delimiter="\t", lineterminator="\n")
        writer.writerow(["read_id", "sample", "length", "n_fraction", "passed"])
        for identifier, sequence, quality, passed in records:
            writer.writerow([identifier, metadata.get(identifier, "unassigned"), len(sequence),
                             round(sequence.count("N") / len(sequence), 4), str(passed).lower()])
            if passed:
                filtered.write(f"@{identifier}\n{sequence}\n+\n{quality}\n")
    metrics = {"input_read_count": len(records), "passed_read_count": sum(item[3] for item in records),
               "total_bases": sum(len(item[1]) for item in records),
               "retained_bases": sum(len(item[1]) for item in records if item[3]),
               "unassigned_read_count": sum(item[0] not in metadata for item in records),
               "min_length": minimum, "max_n_fraction": max_n}
    Path(config["metrics_path"]).write_text(json.dumps(metrics, indent=2) + "\n")
    Path(config["report_path"]).write_text("# Synthetic sequence QC\n\n" +
        "\n".join(f"- {key}: {value}" for key, value in metrics.items()) + "\n")
    return metrics


if __name__ == "__main__":
    print(json.dumps(run(yaml.safe_load(Path(sys.argv[1]).read_text()))))
