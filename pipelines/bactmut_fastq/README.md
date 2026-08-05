# bactmut_fastq BioAgent pipeline

This folder is self-contained and can be copied directly to BioAgent's
`pipelines/bactmut_fastq/` directory.

## Dependencies

- Bash
- Python 3.9 or newer
- Conda environment `bactmut` with `minimap2`, `samtools`, and `bcftools`

Create the environment once:

```bash
conda create -y -n bactmut -c conda-forge -c bioconda \
  python=3.11 pyyaml minimap2 samtools bcftools
```
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

Place one FASTQ file at `data/input/example_reads.fastq`, or place one or more
FASTQ files in a directory. The local reference is
`data/input/example_reference.fasta`; BioAgent can replace either input path
in its generated runtime configuration.

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
- `workflow.py`: consolidated configuration adapter and BactMut FASTQ
  implementation; it validates paths, calls variants, and publishes the
  declared BioAgent outputs.
- `DESCRIPTION.md`: short pipeline description for users and agents.
- `README.md`: dependencies, installation, and configuration.

## BioAgent packaged workflow

`reads` accepts either one single-end FASTQ file or a directory containing
single-end and/or recognizably paired FASTQs. `reference` is required for the
default `params.reference_mode: local`; `species` and `taxonid` instead require
the GTDB environment variables documented above.

The entrypoint deliberately uses the dedicated Conda environment named by the
top-level `environment` field in `config.yaml` (default: `bactmut`). It must
contain modern `minimap2`, `samtools`, and `bcftools`; the pipeline converts
SAM to BAM explicitly before sorting, so it does not rely on ambiguous format
detection.

Run a configured direct job with:

```bash
./run.sh config.yaml
```

In BioAgent, provide `pipeline_name: bactmut_fastq`, `reads`, and `reference`.
The adjustable parameters are `threads`, `min_coverage`, `window_size`,
`step_size`, `sd_threshold`, `reference_mode`, and `verbose`. A single sample
can validly skip the optional tree while producing the required report,
metrics, SNP matrix, and variant files.

Database/reference policy is summarized in
[`../../DATABASE_REQUIREMENTS.md`](../../DATABASE_REQUIREMENTS.md): the normal
`local` mode uses the `reference` input and does not need GTDB; GTDB is needed
only for `species` or `taxonid` reference selection. On the validated server,
set `GTDB_DB_PATH` to
`/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/bacterial_reference_res96_v2/representative.fa.filter_sp_mag`
and `GTDB_METADATA_PATH` to
`/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/bacterial_reference_res96_v2/bac120_metadata.tsv.deversion`.
