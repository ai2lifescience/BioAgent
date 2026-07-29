# Metagenomics-Toolkit

This adapter exposes the upstream DSL2 Metagenomics-Toolkit through BioAgent's
synchronous pipeline runner.

## Inputs

- `params_file`: a native Metagenomics-Toolkit YAML file.
- `execution_mode`: `full` or `standalone`.
- `module`: required only for `standalone`, and must identify exactly one entry
  from `module_catalog.yaml`.

Full mode requires non-empty `input` and `steps` mappings. Standalone mode
requires the YAML's `steps` mapping to contain exactly the selected module's
native step key.

## Outputs

- the complete toolkit result directory;
- Nextflow and toolkit logs;
- a compact BioAgent Markdown report;
- JSON run metrics.

The upstream output hierarchy remains unchanged beneath the result directory.
