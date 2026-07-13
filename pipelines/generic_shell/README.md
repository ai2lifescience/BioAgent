# Generic Shell Pipeline

This is the simplest plug-and-play shell pipeline template for BioAgent.

## Files

```text
pipelines/generic_shell/
  runner.yaml   # how BioAgent runs the pipeline
  config.yaml   # default base config selected by runner.yaml config:
  run.sh        # shell entrypoint selected by runner.yaml entrypoint:
```

## Config

Use this shape for easy agent execution:

```yaml
label: generic_shell
input_path: data/example_reads.txt
output_dir: output
report_path: output/report.md
metrics_path: output/metrics.json
normalized_path: output/normalized.txt
params:
  normalize_mode: whitespace
  uppercase: false
```

When the web UI uploads a file, BioAgent replaces `input_path` in the generated
runtime config. When the agent runs the pipeline, BioAgent resolves declared
output file keys such as `report_path`, `metrics_path`, and `normalized_path`
inside the per-run pipeline artifact directory.

## Runner

Keep `runner.yaml` small:

```yaml
name: generic_shell
engine: shell
config: config.yaml
entrypoint: run.sh
timeout: 120
inputs:
  reads:
    label: Reads text
    config_key: input_path
    required: true
    accepts: [".txt", ".fastq", ".fq", ".fasta", ".fa"]
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
  normalized_text:
    config_key: normalized_path
    default: output/normalized.txt
    kind: text
    required: true
```

BioAgent automatically lets requests override keys under `params`.

Example:

```text
Run the shell pipeline with input_path: "runtime/sessions/<session_id>/artifacts/uploads/reads.txt" uppercase true
```
