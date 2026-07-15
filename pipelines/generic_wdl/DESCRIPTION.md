# Generic WDL Pipeline Description

## Function

This WDL 1.0 pipeline demonstrates sequence normalization and basic FASTA
metrics through BioAgent's WDL runner.

```text
FASTA
  -> remove headers and non-sequence punctuation
  -> optionally uppercase and relabel the sequence
  -> calculate length, GC percentage, and minimum-length status
  -> write normalized FASTA, metrics, and report
```

## Inputs

- `GenericWdl.input_fasta`: required FASTA file.
- `GenericWdl.label`: output FASTA label and report label.
- `GenericWdl.min_length`: minimum length used by the pass/fail metric.
- `GenericWdl.uppercase`: whether to uppercase the normalized sequence.

## Outputs

- `normalized.fasta`: cleaned sequence wrapped at 80 characters.
- `metrics.json`: sequence length, GC percentage, and minimum-length result.
- `report.md`: human-readable metric summary.

BioAgent copies these WDL outputs to `data/output/` as declared in
`runner.yaml`.
