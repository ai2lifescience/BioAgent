# bactmut_fastq BioAgent pipeline

This folder is self-contained and can be copied directly to BioAgent's
`pipelines/bactmut_fastq/` directory.

## Dependencies

- Bash
- Python 3.9 or newer
- PyYAML (`python3 -m pip install pyyaml`)
- `minimap2`
- `samtools`
- `bcftools`
- IQ-TREE 2 (`iqtree2`) or IQ-TREE 1 (`iqtree`) for optional phylogeny

`minimap2`, `samtools`, and `bcftools` are required and must be on `PATH`.
IQ-TREE is optional; the required report, metrics, matrix, and variant outputs
are still generated when a tree cannot be built.

For `params.reference_mode: species` or `taxonid`, also define:

```bash
export GTDB_DB_PATH=/path/to/gtdb_representatives.fasta
export GTDB_METADATA_PATH=/path/to/bac120_metadata.tsv
```

No database is needed for the default `local` reference mode.

## Installation

```bash
unzip bactmut_fastq.zip
cp -R bactmut_fastq /path/to/BioAgent/pipelines/
chmod +x /path/to/BioAgent/pipelines/bactmut_fastq/run.sh
```

Place FASTQ files in `data/input/fastq/` and the local reference in
`data/input/reference.fasta`, or let BioAgent replace those paths in its
generated `config.runtime.yaml`.

## FASTQ naming

The pipeline accepts single-end reads and common paired-end naming conventions,
including `_R1`/`_R2`, `.R1`/`.R2`, `_1`/`_2`, and `.1`/`.2`, with optional
lane/chunk suffixes. Compressed `.gz` inputs are supported.

## Configuration

All input and output paths are top-level keys in `config.yaml`. Only values
under `params` are runtime algorithm parameters intended for BioAgent
overrides.

- `reference_mode`: `local`, `species`, or `taxonid`
- `threads`: CPUs used for mapping, calling, and IQ-TREE
- `min_coverage`: fraction of samples required to cover a position
- `window_size`, `step_size`, `sd_threshold`: recombination filter controls
- `verbose`: detailed logging

The reference input in `runner.yaml` is conditionally required: local-reference
runs need `reference_path`, while `species` and `taxonid` modes resolve it from
the configured GTDB database.

## Direct test

BioAgent calls the entrypoint with a generated runtime configuration:

```bash
./run.sh config.runtime.yaml
```

For a standalone check, copy `config.yaml` to `config.runtime.yaml`, populate
the configured input paths, and run the same command.

## Included files

- `runner.yaml`: BioAgent engine, input, output, timeout, and override contract.
- `config.yaml`: plug-and-play default paths and parameters.
- `run.sh`: strict shell entrypoint; validates and parses the YAML, then starts
  the adapter.
- `bactmut_fastq/config_runner.py`: validates config, invokes the original
  pipeline, publishes configured paths, and creates BioAgent report/metrics.
- `bactmut_fastq/*.py`: original BactMut FASTQ implementation.
- `DESCRIPTION.md`: short pipeline description for users and agents.
- `README.md`: dependencies, installation, and configuration.
