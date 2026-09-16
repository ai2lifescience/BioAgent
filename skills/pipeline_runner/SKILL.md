# Pipeline Runner Skill (local runtime)

Use the `pipeline_shell` Agents SDK local runtime tool to run an approved
pipeline folder under `tools/runtime_tools/pipelines/`. The retired
function-tool wrappers have been removed; pipeline execution uses the local runtime.

Each pipeline folder must contain:

```text
runner.yaml  # BioAgent runner metadata
run.sh, Snakefile, main.nf, or workflow.wdl  # selected by the engine
```

`runner.yaml` selects the engine and is the preferred place for ordinary
defaults:

```yaml
engine: shell
entrypoint: run.sh
params:
  mode: example
```

or:

```yaml
engine: snakemake
snakefile: Snakefile
```

or:

```yaml
engine: nextflow
workflow: main.nf
nextflow_config: nextflow.config  # optional
```

or:

```yaml
engine: wdl
workflow: workflow.wdl
inputs_json: inputs.json   # optional native file
options_json: options.json # optional native file
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

The skill calls only the registered `pipeline_shell` tool and its
`bioagent-pipeline` command protocol. It must not execute arbitrary shell
commands, arbitrary Snakefiles, arbitrary Nextflow workflows,
arbitrary WDL workflows, or paths outside the selected pipeline folder.

Before calling the tool, the skill checks required `runner.yaml` inputs against:

```text
1. user-provided input_path
2. user-provided named input slots, such as sequence: or metadata:
```

The BioAgent skill intentionally does not use bundled input files as runtime
inputs; the user must choose the runtime input explicitly. If a required
input is missing or invalid, the skill returns a user-facing question and does
not call the tool.

For web and API clients, missing-input responses also include structured
`requested_inputs` records. These contain missing or invalid required inputs
and declared optional slots, so upload controls can offer optional paired
inputs without treating them as required:

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

The `plan` command uses workspace-relative paths. Uploaded web files already live
in the current session workspace file directory:

```text
runtime/sessions/<session_id>/uploads/
```

The runtime config passed to Shell, Snakemake, or Nextflow starts from
`runner.yaml` defaults and any explicitly referenced native config, then
BioAgent replaces input paths with selected session inputs and resolves
declared outputs inside the per-run workspace. Use this manifest shape:

```yaml
name: my_pipeline
engine: shell
entrypoint: run.sh
params:
  min_length: 0
  mode: example
inputs:
  sequence: {config_key: input_path, required: true, accepts: [.fasta]}
outputs:
  report: {config_key: report_path, default: report.md, kind: report}
```

Keys under `params` may be changed through `plan --param NAME=VALUE`.
Native files remain optional: use `config: filename.yaml` or
`inputs_json: inputs.json` to load one, and `defaults` for extra native settings.
The merge order is native file, manifest `defaults`, then manifest `params`;
runtime input and parameter selections are applied afterward. Existing
`config.yaml` files are also detected automatically. Explicit file references
must exist inside the pipeline folder.

Default examples:

```text
tools/runtime_tools/pipelines/generic_bio/
tools/runtime_tools/pipelines/generic_shell/
tools/runtime_tools/pipelines/generic_snakemake/
tools/runtime_tools/pipelines/generic_nextflow/
tools/runtime_tools/pipelines/generic_wdl/
```

Nextflow workflows receive the generated YAML through `-params-file`, plus the
runner-managed `bioagent_config_path`, `nextflow_output_dir`, and `cores`
parameters. Publish final files under `nextflow_output_dir` and map them to
declared outputs with each output's relative `nextflow_output` value.
