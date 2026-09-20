# Nextflow pipeline template

This educational Nextflow DSL2 bundle normalizes one FASTA sequence, counts
basic sequence and metadata metrics, and writes a normalized FASTA, JSON
metrics, and Markdown report. It is intended to exercise the Nextflow runtime
contract rather than provide a production analysis.

## Requirements

- Nextflow (a current 22.x/23.x/24.x release is suitable);
- Java 17 or newer;
- Bash and Python 3.10 or newer with PyYAML.

No Docker image, network resource, database, or workflow-managed Conda
installation is needed. Verify the host before running:

```bash
nextflow -version
java -version
python3 -c 'import yaml; print(yaml.__version__)'
```

## Inputs and parameters

`input_path` is a FASTA (`.fa`, `.fasta`, or `.fna`) and `metadata_path` is a
TSV/CSV table. Parameters are `label`, `subtype`, `segment`, `time`,
`analysis_mode`, and `min_length`; runtime-only parameters
`bioagent_config_path` and `nextflow_output_dir` are required by `main.nf`.

The process removes FASTA headers and non-sequence punctuation, uppercases the
sequence, calculates length/GC/minimum-length status, and publishes
`normalized.fasta`, `metrics.json`, and `report.md`.

## Standalone run

Create the small config consumed by `workflow.py`, then pass the engine paths
explicitly:

```bash
cat > config.local.yaml <<'YAML'
label: template_nextflow
params:
  subtype: subtype1
  segment: segment1
  time: all-time
  analysis_mode: example
  min_length: 0
YAML
nextflow run main.nf -c nextflow.config \
  --input_path "$PWD/data/input/sequences_segment1.fasta" \
  --metadata_path "$PWD/data/input/metadata.tsv" \
  --bioagent_config_path "$PWD/config.local.yaml" \
  --nextflow_output_dir "$PWD/output" \
  --label template_nextflow --cores 1
```

The process writes its three published outputs into `output/`. On Windows,
run Nextflow inside WSL because the process uses a POSIX shell.

## BioAgent use and limitations

Use `pipeline_name: template_nextflow` with `sequence` and `metadata`:

```text
Run template_nextflow with its bundled example data and collect the results.
```

The template is a local engine demonstration and does not perform validated
sequence classification or biological interpretation.
