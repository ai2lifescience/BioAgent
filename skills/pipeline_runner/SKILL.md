# Pipeline Runner Skill

Use this skill to run an approved pipeline folder under `pipelines/`.

Each pipeline folder must contain:

```text
runner.yaml  # BioAgent runner metadata
config.yaml  # default base config; can be renamed with runner.yaml config:
```

`runner.yaml` selects the engine and file names:

```yaml
config: config.yaml
engine: shell
entrypoint: run.sh
```

or:

```yaml
config: config.yaml
engine: snakemake
snakefile: Snakefile
```

or:

```yaml
config: config.yaml
engine: nextflow
workflow: main.nf
nextflow_config: nextflow.config  # optional
```

or:

```yaml
engine: wdl
workflow: workflow.wdl
inputs_json: inputs.json
options_json: options.json
```

For multi-input pipelines, `runner.yaml` may also declare named input slots:

```yaml
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
```

The skill calls only the registered `pipeline_runner` tool. It must not execute
arbitrary shell commands, arbitrary Snakefiles, arbitrary Nextflow workflows,
arbitrary WDL workflows, or paths outside the selected pipeline folder.

Before calling the tool, the skill checks required `runner.yaml` inputs against:

```text
1. user-provided input_path
2. user-provided named input slots, such as sequence: or metadata:
```

The BioAgent skill intentionally does not use default input files from
`config.yaml`; the user must choose the runtime input explicitly. If a required
input is missing or invalid, the skill returns a user-facing question and does
not call the tool.

For web and API clients, missing-input responses also include structured
`requested_inputs` records:

```json
[
  {
    "slot": "sequence",
    "label": "Sequence FASTA",
    "config_key": "input_path",
    "accepts": [".fa", ".fasta", ".fna"],
    "reason": "missing"
  }
]
```

By default, the tool uses `input_path` directly. Uploaded web files already live
in the current session artifact directory:

```text
runtime/sessions/<session_id>/artifacts/uploads/
```

The runtime config passed to Shell, Snakemake, Nextflow, or WDL starts from the
configured base config/input file, then BioAgent replaces input paths with the
selected session input paths and resolves declared outputs inside the per-run
pipeline artifact directory. Use this simple base config shape for Shell,
Snakemake, and Nextflow plug-and-play pipelines:

```yaml
label: my_pipeline
input_path: path/to/default/input.file
output_dir: output
params:
  min_length: 0
  mode: example
```

Keys under `params` may be changed through `config_overrides`.

Default examples:

```text
pipelines/generic_bio/
pipelines/generic_shell/
pipelines/generic_snakemake/
pipelines/generic_nextflow/
pipelines/generic_wdl/
```

Nextflow workflows receive the generated YAML through `-params-file`, plus the
runner-managed `bioagent_config_path`, `nextflow_output_dir`, and `cores`
parameters. Publish final files under `nextflow_output_dir` and map them to
declared artifacts with each output's relative `nextflow_output` value.
