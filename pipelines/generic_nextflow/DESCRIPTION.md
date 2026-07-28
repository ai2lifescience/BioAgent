# Generic Nextflow Pipeline Description

## Function

This pipeline demonstrates BioAgent's Nextflow engine with a small local
sequence-analysis workflow. It normalizes a FASTA sequence, calculates basic
metrics, and creates a Markdown report.

```text
FASTA + metadata
  -> Nextflow stages declared inputs
  -> normalize sequence characters
  -> calculate length, GC percentage, and minimum-length status
  -> publish normalized FASTA, metrics, and report
```

## Inputs

- `input_path`: required FASTA input (`.fa`, `.fasta`, or `.fna`).
- `metadata_path`: required TSV or CSV metadata table.

## Outputs

- `normalized.fasta`: normalized sequence with the configured label and segment.
- `metrics.json`: sequence, metadata, and configured analysis metrics.
- `report.md`: human-readable metric summary.

Nextflow first publishes these files to BioAgent's engine staging directory.
The runner then maps each `nextflow_output` declared in `runner.yaml` to the
stable per-run artifact path declared by that output record.
