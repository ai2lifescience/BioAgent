# Metagenomic pathogen identification

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Identify bacterial, viral, fungal, and parasite signals from host-filtered reads using alignment, cross-database arbitration, and confidence filtering.

## Inputs

- `sequence_file1` (required, `MetagenomicDetection.sequence_file1`): Required host-filtered read 1 input.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.
- `sequence_file2` (optional, `MetagenomicDetection.sequence_file2`): Optional host-filtered read 2 input.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.

## Outputs

- `final_report`: `data/output/priority_with_confidence.tsv` — Priority panel with confidence produced by this workflow..
- `priority_panel`: `data/output/priority_microbe_panel.tsv` — Stage 5 priority microbe panel produced by this workflow..
- `sample_overview`: `data/output/sample_overview.tsv` — Sample overview produced by this workflow..
- `read_accounting`: `data/output/stage2_read_accounting.tsv` — Stage 2 read accounting produced by this workflow..
- `crossdb_signature`: `data/output/stage2_crossdb_signature.tsv` — Stage 2 cross-database signature produced by this workflow..

## Run

Ask the agent to run `metagenomic_pathogen_identification` with the inputs above. For the bundled example, say:

```text
Run metagenomic_pathogen_identification with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
