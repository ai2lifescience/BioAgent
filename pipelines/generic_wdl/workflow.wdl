version 1.0

workflow GenericWdl {
  input {
    File input_fasta
    String label = "generic_wdl"
    Int min_length = 0
    Boolean uppercase = true
  }

  call AnalyzeFasta {
    input:
      input_fasta = input_fasta,
      label = label,
      min_length = min_length,
      uppercase = uppercase
  }

  output {
    File report = AnalyzeFasta.report
    File metrics = AnalyzeFasta.metrics
    File normalized_fasta = AnalyzeFasta.normalized_fasta
  }
}

task AnalyzeFasta {
  input {
    File input_fasta
    String label
    Int min_length
    Boolean uppercase
  }

  command <<<
    set -euo pipefail

    python3 <<'PY'
    import json
    import re

    input_path = "~{input_fasta}"
    label = "~{label}"
    min_length = int("~{min_length}")
    uppercase = "~{uppercase}".lower() == "true"

    sequence_parts = []
    with open(input_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith(">"):
                continue
            sequence_parts.append(re.sub(r"[^A-Za-z*-]", "", line))

    sequence = "".join(sequence_parts)
    if uppercase:
        sequence = sequence.upper()

    with open("normalized.fasta", "w", encoding="utf-8") as handle:
        handle.write(f">{label}\n")
        for index in range(0, len(sequence), 80):
            handle.write(sequence[index:index + 80] + "\n")

    gc_count = sequence.count("G") + sequence.count("C")
    metrics = {
        "status": "ok",
        "pipeline": "generic_wdl",
        "label": label,
        "sequence_length": len(sequence),
        "min_length": min_length,
        "passes_min_length": len(sequence) >= min_length,
        "gc_percent": round((gc_count / len(sequence) * 100) if sequence else 0, 2),
    }
    with open("metrics.json", "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    with open("report.md", "w", encoding="utf-8") as handle:
        handle.write("# Generic WDL Pipeline Report\n\n")
        handle.write(f"- Label: {label}\n")
        handle.write(f"- Input: {input_path}\n")
        handle.write(f"- Sequence length: {metrics['sequence_length']}\n")
        handle.write(f"- Minimum length: {min_length}\n")
        handle.write(f"- Passes minimum length: {metrics['passes_min_length']}\n")
        handle.write(f"- GC percent: {metrics['gc_percent']}\n")
    PY
  >>>

  output {
    File report = "report.md"
    File metrics = "metrics.json"
    File normalized_fasta = "normalized.fasta"
  }

  runtime {
    docker: "python:3.11-slim"
  }
}
