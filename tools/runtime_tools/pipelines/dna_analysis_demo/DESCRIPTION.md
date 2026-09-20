# Generic Bioinformatics Pipeline Description

## Function

This educational pipeline demonstrates a fuller set of files and stages seen
in a DNA sequencing workflow without requiring an external aligner or variant
caller.

```text
FASTQ reads + reference FASTA + sample metadata
  -> validate records and metadata
  -> calculate per-read and per-base QC
  -> filter reads by length and mean quality
  -> create demonstration SAM alignments
  -> calculate positional coverage and consensus
  -> call demonstration SNVs
  -> emit sequences, alignments, tables, figures, metrics, and reports
```

## Inputs

- `reads` / `input_path`: single-end FASTQ (`.fastq`, `.fq`, and gzip
  equivalents) using Phred+33 quality characters.
- `reference` / `reference_path`: a FASTA file containing exactly one DNA
  reference sequence.
- `metadata` / `metadata_path`: TSV or CSV sample metadata with a unique
  `sample_id` column.

## Sequence, alignment, and variant outputs

- `filtered_reads.fastq`: reads passing the configured length and quality
  filters.
- `alignments.sam`: demonstration SAM records for retained reads.
- `consensus.fasta`: consensus sequence across retained reads.
- `variants.vcf`: SNV-like differences between the reference and positional
  consensus in VCF 4.2 format.

## Table outputs

- `read_qc.tsv`: length, GC percentage, mean quality, Q20/Q30 base counts, and
  filter status for every input read.
- `sample_summary.tsv`: sample metadata joined to headline QC and analysis
  metrics.
- `coverage.tsv`: per-reference-position depth, nucleotide counts, consensus,
  and variant status.
- `variant_summary.tsv`: a flat, spreadsheet-friendly variant table.

## Figures and reports

- `qc_overview.png`: read length, read quality, GC, and filtering panels.
- `coverage.png`: high-quality base depth across the reference.
- `variant_allele_fraction.png`: allele fractions for passing variants.
- `metrics.json`: machine-readable input, filtering, coverage, and variant
  metrics.
- `report.md`: portable Markdown report with embedded figure links.
- `report.html`: styled, self-contained HTML summary linking all artifacts.

## Optional phylogenetic outputs

By default, `emit_phylogenetic_tree` is enabled and the pipeline additionally
creates:

- `phylogenetic_tree.nwk`: Newick representation of a two-tip
  reference-versus-consensus demonstration tree.
- `phylogenetic_tree.png`: rendered tree figure.

These outputs remain conditional: set `emit_phylogenetic_tree` to `false` to
omit them from the download list. A real phylogenetic analysis requires
multiple biological sequences, an appropriate alignment, and a validated
inference method.

## Scope and limitation

The pipeline assumes each read starts at reference position 1. This keeps the
demo deterministic and dependency-light, but it is not an alignment algorithm.
The SAM and VCF are format demonstrations only and must not be used for
research or clinical interpretation. A real workflow should use validated
tools for read alignment, duplicate handling, recalibration, and variant
calling.
