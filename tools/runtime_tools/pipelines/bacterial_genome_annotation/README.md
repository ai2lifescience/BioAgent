# Bacterial genome annotation

This bundle annotates assembled bacterial contigs with Prokka or Bakta and
normalizes their different file layouts into one stable output contract. It
implements the capability directly and does not import Biomni.

## Requirements

- Bash and Python 3.11 or newer;
- PyYAML available to the Python interpreter;
- `prokka` for the default annotator, or `bakta` plus a compatible Bakta database.

A convenient environment is:

```bash
conda create -n bacterial-annotation -c conda-forge -c bioconda \
  python=3.12 pyyaml prokka bakta
conda activate bacterial-annotation
prokka --version
bakta --version
```

For Bakta, download a database once outside the run and set `params.bakta_db_path`
or `BAKTA_DB`:

```bash
bakta_db download --output /opt/bakta-db --type full
```

The database is not included in this bundle.

## Inputs and parameters

`genome_path` is one assembled bacterial FASTA (`.fasta`, `.fa`, or `.fna`).
The runtime YAML is based on `config.yaml`; edit `genome_path` and `output_dir`
before running. Parameters under `params` include:

- `annotator`: `prokka` (default) or `bakta`;
- `prefix`, `genus`, `species`, `strain`, `cpus`, `translation_table`, and
  `locus_tag`;
- Bakta-only `bakta_db_path`, `gram`, `meta`, `complete`, and
  `keep_contig_headers`;
- Prokka-only `rfam` and the shared `compliant` flag.

Translation tables are limited to 4, 11, and 25. The pipeline rejects unknown
annotators, incompatible engine-specific options, and simultaneous Bakta
`meta` and `complete` modes.

## Standalone installation and run

Copy the directory to a host with the tools, make the entrypoint executable, and
edit a copy of the configuration:

```bash
chmod +x run.sh
cp config.yaml config.local.yaml
# Set genome_path and output_dir; adjust params as needed.
./run.sh config.local.yaml
```

The same operation can be run with `python workflow.py config.local.yaml`.
The command records the selected executable and version in `metrics.json` and
validates the expected output files.

## Outputs

Required outputs are:

- `annotation.gff`, `annotation.gbk`, `annotation.faa`, `annotation.ffn`, and
  `annotation.fna`;
- `annotation.tsv`, `annotation.txt`, `annotation.log`,
  `annotation_outputs.zip`, `metrics.json`, and `report.md`.

Bakta may additionally produce `annotation.json`, inference and hypothetical
protein tables, and SVG/PNG plots. The archive contains the unmodified tool
output, while normalized files keep the contract identical between Prokka and
Bakta runs.

## BioAgent use and interpretation

Use `pipeline_name: bacterial_genome_annotation` and provide `genome`. For the
bundled fixture:

```text
Run bacterial_genome_annotation with its bundled example data and collect the results.
```

Pin both the executable and database version when comparing annotations. Output
quality depends on assembly quality, organism metadata, database release, and
the selected annotation engine.
