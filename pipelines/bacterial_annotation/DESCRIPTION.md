# Bacterial Annotation Pipeline Description

## Function

The pipeline accepts an assembled bacterial genome in FASTA format, runs
Prokka, validates the expected output set, and writes stable filenames for
BioAgent artifact handling.

```text
assembled contigs
  -> FASTA validation
  -> Prokka annotation
  -> output validation and normalization
  -> metrics, report, and complete ZIP bundle
```

Unlike the original Biomni wrapper, this pipeline returns structured metrics
and declares every important output through `runner.yaml`.

## Input

The required `genome` slot accepts `.fa`, `.fasta`, or `.fna` files. The input
must contain at least one non-empty FASTA record.

Optional request parameters are:

- `prefix`: Prokka output prefix; restricted to safe filename characters.
- `genus`: organism genus.
- `species`: organism species epithet.
- `strain`: strain identifier.
- `cpus`: Prokka CPU count from 1 through 256.

## Outputs

- `annotation.gff`: combined GFF3 annotation and sequences.
- `annotation.gbk`: GenBank annotation.
- `annotation.faa`: translated protein sequences.
- `annotation.ffn`: nucleotide sequences for annotated features.
- `annotation.fna`: input contigs normalized by Prokka.
- `annotation.tsv`: tabular feature annotations.
- `annotation.txt`: Prokka annotation statistics.
- `prokka.log`: executed command and captured standard output/error.
- `metrics.json`: structured input, runtime, taxonomy, and feature metrics.
- `report.md`: human-readable run summary.
- `prokka_outputs.zip`: complete unmodified Prokka output directory.

All outputs are written into the active session's per-run pipeline artifact
directory. User-supplied text is passed to Prokka as subprocess arguments; the
pipeline does not invoke a shell or accept arbitrary extra arguments.

## Mock fixtures

`data/input/example_contigs.fasta` contains two artificial contigs totaling 564
bases. `data/output/` contains representative GFF3, GenBank, protein FASTA,
gene FASTA, feature table, summary, metrics, log, and report files. These
fixtures document the contract and support no-network tests; they are not real
annotation results.
