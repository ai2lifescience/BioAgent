# Metagenomic QC Pipeline Description

## Function

The WDL 1.0 workflow performs read quality control and sequential host removal.

```text
single-end or paired-end FASTQ
  -> fastp quality and length filtering
  -> Kraken2 host filtering
  -> Bowtie2 host/vector filtering
  -> cleaned FASTQ and read-count tables
```

## Inputs

- `MetagenomicQc.fastq_r1`: required read 1 (`.fastq`, `.fq`, `.fastq.gz`,
  or `.fq.gz`). Compression is detected from file content, not the suffix.
- `MetagenomicQc.fastq_r2`: optional read 2, same FASTQ / FASTQ.GZ formats.
  Its presence selects the paired-end task; otherwise the single-end task is
  used. The two files need not use the same compression.
- `MetagenomicQc.kraken2_db_files`: mounted Kraken2 database file paths.
- `MetagenomicQc.host_bowtie2_index_files`: mounted host Bowtie2 index paths.
- `sample_id`, `lean_io_mode`, Docker image, CPU, memory, and disk settings.

## Outputs

- `clean.R1.fq`: cleaned single-end reads or paired-end read 1.
- `clean.R2.fq`: paired-end read 2; absent for single-end runs.
- `qc_counts.tsv`: input, post-QC, and post-host-removal read counts.
- `phase1_read_overview.tsv`: one-row sample-level read overview.

`post_host_reads` is also returned as an integer WDL output. BioAgent collects
the four file outputs declared in `runner.yaml` after Cromwell succeeds.
