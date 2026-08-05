# bactmut_fasta BioAgent pipeline

This folder is self-contained and can be copied directly to BioAgent's
`pipelines/bactmut_fasta/` directory.

## Dependencies

- Bash
- Python 3.9 or newer
- PyYAML (`python3 -m pip install pyyaml`)
- `minimap2` for contig assemblies or genomes with indels
- IQ-TREE 2 (`iqtree2`) or IQ-TREE 1 (`iqtree`) for phylogeny

The Python pipeline itself uses only the standard library. With
`params.aligner: auto`, it uses `minimap2` when available and otherwise falls
back to the internal aligner. The internal aligner only supports equal-length,
full-genome FASTA sequences.

For `params.reference_mode: species` or `taxonid`, also define:

```bash
export GTDB_DB_PATH=/path/to/gtdb_representatives.fasta
export GTDB_METADATA_PATH=/path/to/bac120_metadata.tsv
```

No database is needed for the default `local` reference mode.

## Installation

```bash
unzip bactmut_fasta.zip
cp -R bactmut_fasta /path/to/BioAgent/pipelines/
chmod +x /path/to/BioAgent/pipelines/bactmut_fasta/run.sh
```

Place at least five query FASTA files in `data/input/genomes/` and the local
reference in `data/input/reference.fasta`, or let BioAgent replace those paths
in its generated `config.runtime.yaml`.

## Configuration

All input and output paths are top-level keys in `config.yaml`. Only values
under `params` are runtime algorithm parameters intended for BioAgent
overrides.

- `reference_mode`: `local`, `species`, or `taxonid`
- `threads`: worker/thread budget
- `aligner`: `auto`, `minimap2`, or `internal`
- `min_coverage`: fraction of samples required to cover a position
- `window_size`, `step_size`, `sd_threshold`: recombination filter controls
- `simulate`: generate validation genomes instead of reading `input_path`
- `simulate_snp_rate`, `simulate_samples`, `seed`: simulation controls
- `verbose`: detailed logging

The input and reference entries in `runner.yaml` are conditionally required:
real-data runs need `input_path`, local-reference runs need `reference_path`,
and simulation/database-reference modes intentionally omit one of them.

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
- `bactmut_fasta/config_runner.py`: validates config, invokes the original
  pipeline, publishes configured paths, and creates BioAgent report/metrics.
- `bactmut_fasta/*.py`: original BactMut FASTA implementation.
- `DESCRIPTION.md`: short pipeline description for users and agents.
- `README.md`: dependencies, installation, and configuration.
