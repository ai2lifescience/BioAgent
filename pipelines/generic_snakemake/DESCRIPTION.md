# Generic Snakemake Pipeline Description

## Function

This pipeline demonstrates a small sequence-analysis workflow implemented with
Snakemake. It cleans and combines the input FASTA sequence content, calculates
basic metrics, and creates a Markdown report.

```text
FASTA + metadata
  -> normalize sequence characters
  -> calculate length, GC percentage, and minimum-length status
  -> write normalized FASTA, metrics, and report
```

## Inputs

- `input_path`: required FASTA input (`.fa`, `.fasta`, or `.fna`).
- `metadata_path`: required TSV or CSV metadata table. The example workflow
  reports its number of data rows.

All non-header FASTA lines are combined, non-sequence punctuation is removed,
and the resulting sequence is converted to uppercase.

## Outputs

- `normalized.fasta`: combined normalized sequence labeled with the configured
  pipeline label and segment.
- `metrics.json`: sequence length, GC percentage, metadata row count,
  minimum-length result, and analysis parameters.
- `report.md`: human-readable summary of the metrics.

The default run writes the complete generated output set under `data/output/`.
