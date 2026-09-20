# Pathogen variant risk assessment

> Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

Align pathogen reads, call and annotate variants, and produce a pathogen-specific risk-assessment report.

## Inputs

- `read1` (required, `VariantRisk.fastq_r1`): Read 1 FASTQ input.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.
- `read2` (optional, `VariantRisk.fastq_r2`): Optional read 2 FASTQ input for paired-end processing.. Accepted: .fastq, .fq, .fastq.gz, .fq.gz.

## Outputs

- `final_report`: `data/output/final_variant_risk_report.tsv` — Final variant risk report produced by this workflow..
- `segments`: `data/output/segments.tsv` — Segment depth summary produced by this workflow..
- `output_archive`: `data/output/risk_assessment_output.tar` — Complete risk assessment output produced by this workflow..

## Run

Ask the agent to run `pathogen_variant_risk_assessment` with the inputs above. For the bundled example, say:

```text
Run pathogen_variant_risk_assessment with its bundled example data and collect the results.
```

The `runner.yaml` file is the agent-facing input/output contract. The runtime stages inputs and writes declared outputs inside the per-run workspace.
