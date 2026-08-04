# Bacterial Annotation Pipeline Environment

This pipeline annotates assembled bacterial genomes with either Prokka or
Bakta and exposes a stable set of BioAgent artifacts. Prokka remains the
default for compatibility with the original Biomni-style function. Bakta is
recommended for new analyses that can use its maintained, versioned database.

## Ubuntu requirements

- Bash and Python 3.11 or newer.
- PyYAML, already included in the BioAgent requirements.
- Prokka and/or Bakta available on `PATH`.
- A compatible Bakta database when `annotator: bakta` is selected.

One Bioconda environment can provide both executables:

```bash
conda create -n bacterial-annotation -c conda-forge -c bioconda \
  python=3.12 prokka bakta
conda activate bacterial-annotation
prokka --version
bakta --version
```

Download the Bakta database once, outside pipeline execution:

```bash
bakta_db download --output /opt/bakta-db --type full
```

Use the exact downloaded database directory as `bakta_db_path`, or export it
as `BAKTA_DB`. Start BioAgent from the same activated environment.

## Run with Prokka

```text
annotate_bacterial_genome genome: "path/to/contigs.fasta" annotator prokka genus Escherichia species coli strain "K-12" cpus 4
```

Because Prokka is the compatibility default, `annotator prokka` can be omitted.

## Run with Bakta

```text
annotate_bacterial_genome genome: "path/to/contigs.fasta" annotator bakta bakta_db_path: "/opt/bakta-db/db" genus Escherichia species coli strain "K-12" translation_table 11 gram - cpus 8
```

The natural form `Annotate bacterial genome "contigs.fasta" using Bakta` also
selects Bakta, but a database must still be supplied in the request or through
`BAKTA_DB`.

## Example data

The artificial input is located at:

```text
pipelines/bacterial_annotation/data/input/example_contigs.fasta
```

Committed outputs under `data/output/` are clearly marked synthetic fixtures.
The root of that folder documents the Prokka contract; `data/output/bakta/`
documents Bakta normalization and Bakta-specific artifacts.
