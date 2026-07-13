# Generic Snakemake Pipeline

This is the simplest plug-and-play Snakemake pipeline template for BioAgent.

## Files

```text
pipelines/generic_snakemake/
  runner.yaml   # how BioAgent runs the pipeline
  config.yaml   # default base config selected by runner.yaml config:
  Snakefile     # workflow selected by runner.yaml snakefile:
  data/         # example input data
```

## Config

Use this shape for easy agent execution:

```yaml
label: generic_snakemake
input_path: data/sequences_segment1.fasta
metadata_path: data/metadata.tsv
output_dir: output
report_path: output/report.md
metrics_path: output/metrics.json
normalized_fasta_path: output/normalized.fasta
params:
  subtype: subtype1
  segment: segment1
  time: all-time
  analysis_mode: example
  min_length: 0
```

When the web UI uploads a file, BioAgent replaces `input_path` in the generated
runtime config. When the agent runs the pipeline, BioAgent resolves declared
output file keys such as `report_path`, `metrics_path`, and
`normalized_fasta_path` inside the per-run pipeline artifact directory.

## Runner

Keep `runner.yaml` small:

```yaml
name: generic_snakemake
engine: snakemake
config: config.yaml
snakefile: Snakefile
cores: 1
timeout: 300
inputs:
  sequence:
    label: Sequence FASTA
    config_key: input_path
    required: true
    accepts: [".fa", ".fasta", ".fna"]
  metadata:
    label: Metadata table
    config_key: metadata_path
    required: true
    accepts: [".tsv", ".csv"]
outputs:
  report:
    config_key: report_path
    default: output/report.md
    kind: report
    required: true
  metrics:
    config_key: metrics_path
    default: output/metrics.json
    kind: metrics
    required: true
  normalized_sequence:
    config_key: normalized_fasta_path
    default: output/normalized.fasta
    kind: sequence
    required: true
```

BioAgent automatically lets requests override keys under `params`.

Example:

```text
Run the snakemake pipeline with pipeline_name: generic_snakemake input_path: "runtime/sessions/<session_id>/artifacts/uploads/sequences.fasta" min_length 50
```
