# Metagenomic read quality control

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Filter metagenomic reads and remove host or vector sequences with fastp, Kraken2, and Bowtie2 before downstream analysis.

## Inputs

- `read1` (required, `MetagenomicQc.fastq_r1`): Read 1 FASTQ input.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.
- `read2` (optional, `MetagenomicQc.fastq_r2`): Optional read 2 FASTQ input for paired-end processing.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.

## Outputs

- `clean_r1`: `data/output/clean.R1.fq` — Host-filtered read 1 produced by this workflow..
- `clean_r2`: `data/output/clean.R2.fq` — Host-filtered read 2 produced by this workflow..
- `qc_counts`: `data/output/qc_counts.tsv` — QC read counts produced by this workflow..
- `phase1_metrics`: `data/output/phase1_read_overview.tsv` — Phase 1 read overview produced by this workflow..

## Run

Ask the agent to run `metagenomic_read_quality_control` with the inputs above. For the bundled example, say:

```text
Run metagenomic_read_quality_control with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
