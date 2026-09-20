# Alignment-based Identification Pipeline Description

## Function

This WDL 1.0 workflow performs post-QC metagenomic pathogen detection against
optional bacteria, virus, fungi, and parasite minimap2 indexes.

```text
host-filtered FASTQ (R1[, R2])
  -> Stage 1 parallel minimap2 mapping
  -> Stage 2 cross-database arbitration
  -> Stage 3 taxon assignment
  -> Stage 4 genome coverage metrics
  -> Stage 5 priority panel / sample overview
  -> Stage 6 confidence filtering
```

## Inputs

- `MetagenomicDetection.sequence_file1`: required host-filtered read 1
  (`.fastq`, `.fq`, `.fastq.gz`, or `.fq.gz`; typically from the `qc`
  pipeline). Compression is detected from file content, not the suffix.
- `MetagenomicDetection.sequence_file2`: optional read 2 for paired-end runs,
  same FASTQ / FASTQ.GZ formats as read 1 (the two files need not match).
- Optional database paths: `db_bacteria`, `db_virus`, `db_fungi`,
  `db_parasite` (omit unused types; do not pass empty strings).
- Annotation tables: `anno_pathogen`, `anno_virus`, `non_report_list`,
  optional `white_list` and `posstat_file`.
- Mapping and Stage 6 filter thresholds, Docker image, and resource settings.

## Outputs

- `priority_with_confidence.tsv`: Stage 6 final confidence-filtered panel.
- `priority_microbe_panel.tsv`: Stage 5 priority panel.
- `sample_overview.tsv`: sample-level overview.
- `stage2_read_accounting.tsv` / `stage2_crossdb_signature.tsv`: arbitration
  summaries.

BioAgent submits through Cromwell, polls until `Succeeded`, and collects the
outputs declared in `runner.yaml`.
