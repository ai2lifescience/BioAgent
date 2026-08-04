# Metagenomics-Toolkit integration

BioAgent runs a pinned Metagenomics-Toolkit checkout synchronously through its
Nextflow runner. Exactly two execution forms are supported:

- `full`: run the toolkit's `wFullPipeline` entry with a native toolkit YAML;
- `standalone`: run exactly one approved named module with a native module YAML.

## Linux environment

Install Java 17 or newer, Nextflow, and Docker. Point BioAgent at the toolkit
checkout before starting the CLI, API, or web server:

```bash
export METAGENOMICS_TK_PATH=/opt/metagenomics-tk
```

The adapter requests Nextflow 25.10.4, uses the `standard` profile, enables
`-resume`, publishes durable copies rather than work-directory symlinks, and
does not impose a subprocess timeout.

## Full pipeline

Supply a native toolkit parameter YAML containing non-empty `input` and
`steps` mappings:

```text
Run pipeline with pipeline_name: metagenomics_toolkit params_file: "/data/full.yml" execution_mode: full
```

## One standalone module

The parameter YAML must contain exactly the corresponding step. For example,
`annotation.yml` must contain only `steps.annotation`:

```text
Run pipeline with pipeline_name: metagenomics_toolkit params_file: "/data/annotation.yml" execution_mode: standalone module: annotation
```

Approved module names are listed in `module_catalog.yaml`. Relative paths
inside a native toolkit YAML are evaluated by Nextflow from the run directory;
use absolute paths on the Linux server for local input files and databases.
