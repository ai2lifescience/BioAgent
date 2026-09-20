# Metagenomic de novo assembly

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Assemble metagenomic reads, identify assembled contigs against configured reference databases, and produce contig- and species-level reports.

## Inputs

- `read1` (required, `AssemblyId.fastq_r1`): Read 1 FASTQ input.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.
- `read2` (optional, `AssemblyId.fastq_r2`): Optional read 2 FASTQ input for paired-end processing.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.

## Outputs

- `contigs`: `data/output/final.contigs.renamed.fa` — Renamed assembled contigs produced by this workflow..
- `contig_report`: `data/output/contig_report.tsv` — Contig identification report produced by this workflow..
- `species_report`: `data/output/species_report.tsv` — Species identification report produced by this workflow..

## Run

Ask the agent to run `metagenomic_de_novo_assembly` with the inputs above. For the bundled example, say:

```text
Run metagenomic_de_novo_assembly with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
