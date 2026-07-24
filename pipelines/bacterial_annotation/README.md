# Bacterial Annotation Pipeline Environment

This pipeline annotates assembled bacterial genomes with Prokka and exposes the
important annotation files as BioAgent session artifacts.

## Requirements

- Bash and Python 3.11 or newer.
- PyYAML, already included in the BioAgent requirements.
- Prokka available on `PATH` together with its databases and command-line
  dependencies.

A pinned Bioconda installation is recommended for reproducibility:

```bash
conda install bioconda::prokka=1.15.6
prokka --version
prokka --listdb
```

Start BioAgent from the same activated environment so its pipeline subprocess
can find `prokka`.

## Run through BioAgent

```text
Run pipeline with pipeline_name: bacterial_annotation genome: "path/to/contigs.fasta" genus Escherichia species coli strain "K-12" prefix ecoli cpus 4
```

The shorter request `Annotate bacterial genome genome: "path/to/contigs.fasta"`
is routed to the same pipeline.

## Example data

An artificial two-contig FASTA is provided at:

```text
pipelines/bacterial_annotation/data/input/example_contigs.fasta
```

Run it through BioAgent with:

```text
Run pipeline with pipeline_name: bacterial_annotation genome: "pipelines/bacterial_annotation/data/input/example_contigs.fasta" genus Mock species bacterium strain example
```

Representative text outputs are committed under `data/output/`. They are
clearly marked mock fixtures and show the expected formats without claiming to
be real Prokka annotations.

Prokka's upstream project recommends Bakta for new long-lived pipelines. This
wrapper intentionally uses Prokka to provide behavior compatible with Biomni's
`annotate_bacterial_genome` function.
